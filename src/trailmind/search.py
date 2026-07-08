from __future__ import annotations

from pathlib import Path


def search_entities(
    repo_root: Path,
    *,
    query: str,
    entity_types: list[str] | None = None,
    project: str | None = None,
    epic: str | None = None,
    limit: int = 30,
) -> list[dict[str, str]]:
    """Search across all entities by keyword in title and body.

    entity_types: filter by type (project, epic, task, issue, milestone, inbox, spec, plan).
                  None means search all types.
    project: filter by project slug.
    epic: filter by epic path or slug.
    """
    query_lower = query.lower()
    projects_dir = repo_root / "projects"
    if not projects_dir.exists():
        return []

    # Collect all entity files with their type
    entity_files: list[tuple[Path, str]] = []

    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        if project and proj_dir.name != project:
            continue

        # PROJECT.md
        proj_md = proj_dir / "PROJECT.md"
        if proj_md.exists():
            entity_files.append((proj_md, "project"))

        for epic_dir in sorted(proj_dir.iterdir()):
            if not epic_dir.is_dir():
                continue
            if epic:
                epic_rel = f"projects/{proj_dir.name}/{epic_dir.name}"
                if epic != epic_rel and epic != epic_dir.name:
                    continue

            epic_md = epic_dir / "EPIC.md"
            if epic_md.exists():
                entity_files.append((epic_md, "epic"))

            # Subdirectories
            type_map = {
                "tasks": "task",
                "issues": "issue",
                "milestones": "milestone",
                "inbox": "inbox",
            }
            for subdir, etype in type_map.items():
                d = epic_dir / subdir
                if d.exists():
                    for f in sorted(d.glob("*.md")):
                        if f.is_file():
                            entity_files.append((f, etype))

            # Specs and plans
            doc_type_map = {"specs": "spec", "plans": "plan"}
            for subdir, etype in doc_type_map.items():
                d = epic_dir / "docs" / subdir
                if d.exists():
                    for f in sorted(d.glob("*.md")):
                        if f.is_file():
                            entity_files.append((f, etype))

    # Search
    results: list[dict[str, str]] = []
    for file_path, etype in entity_files:
        # Apply type filter
        if entity_types and etype not in entity_types:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        content_lower = content.lower()
        if query_lower not in content_lower:
            continue

        # Extract metadata
        rel = file_path.relative_to(repo_root).as_posix()

        # Get title from frontmatter or H1
        title = file_path.stem
        import re
        fm_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        if fm_match:
            title = fm_match.group(1).strip().strip('"').strip("'")
        else:
            h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1).strip()

        # Get entity ID
        entity_id = file_path.stem
        id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
        if id_match:
            entity_id = id_match.group(1).strip().strip('"').strip("'")

        # Get status
        status = ""
        status_match = re.search(r"^status:\s*(.+)$", content, re.MULTILINE)
        if status_match:
            status = status_match.group(1).strip().strip('"').strip("'")

        # Find snippet: the line containing the match, skipping frontmatter
        snippet = ""
        in_frontmatter = False
        fm_count = 0
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "---":
                fm_count += 1
                in_frontmatter = fm_count < 2
                continue
            if in_frontmatter:
                continue
            if query_lower in line.lower():
                clean = line.strip().lstrip("#").strip()
                if clean and len(clean) > 5 and not clean.startswith("## "):
                    snippet = clean[:200]
                    break

        # Calculate relevance score: title match > body match
        title_score = 2 if query_lower in title.lower() else 0
        status_score = 1 if status in ("in_progress", "ready", "open") else 0
        relevance = title_score + status_score

        results.append({
            "entity_type": etype,
            "entity_id": entity_id,
            "title": title,
            "status": status,
            "snippet": snippet,
            "path": rel,
            "_relevance": relevance,
        })

    # Sort by relevance, then by path
    results.sort(key=lambda r: (r["_relevance"], r["path"]), reverse=True)

    # Remove internal key
    for r in results:
        del r["_relevance"]

    return results[:limit]
