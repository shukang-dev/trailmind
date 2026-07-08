from __future__ import annotations

import re
from datetime import date
from pathlib import Path


ACTIVITY_ENTRY_RE = re.compile(
    r"^-\s+(?P<date>\d{4}-\d{2}-\d{2}):\s+"
    r"(?P<action>.+?)\s+by\s+(?P<actor>\S+?)"
    r"[.!?]?(?:\s+(?P<note>.+))?$",
    re.MULTILINE,
)


def collect_activity(
    repo_root: Path,
    *,
    limit: int = 20,
    entity_type: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    project: str | None = None,
    epic: str | None = None,
) -> list[dict[str, str]]:
    """Collect recent activity across all entities.

    Scans PROJECT.md, EPIC.md, T-*.md, I-*.md, M-*.md, IN-*.md files
    for activity log entries and returns them sorted by date (newest first).
    """
    projects_dir = repo_root / "projects"
    if not projects_dir.exists():
        return []

    # Collect all entity files
    entity_files: list[Path] = []

    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        # Apply project filter early
        if project and proj_dir.name != project:
            continue
        # PROJECT.md
        proj_md = proj_dir / "PROJECT.md"
        if proj_md.exists():
            entity_files.append(proj_md)

        for epic_dir in sorted(proj_dir.iterdir()):
            if not epic_dir.is_dir():
                continue
            # Apply epic filter early
            if epic:
                epic_rel = f"projects/{proj_dir.name}/{epic_dir.name}"
                if epic_rel != epic and epic_dir.name != epic:
                    continue
            epic_md = epic_dir / "EPIC.md"
            if epic_md.exists():
                entity_files.append(epic_md)

            # Tasks, issues, milestones, inbox
            for subdir_name in ("tasks", "issues", "milestones", "inbox"):
                subdir = epic_dir / subdir_name
                if not subdir.exists():
                    continue
                for f in sorted(subdir.glob("*.md")):
                    if f.is_file():
                        entity_files.append(f)

            # Specs and plans
            for subdir_name in (("docs", "specs"), ("docs", "plans")):
                subdir = epic_dir / subdir_name[0] / subdir_name[1]
                if not subdir.exists():
                    continue
                for f in sorted(subdir.glob("*.md")):
                    if f.is_file():
                        entity_files.append(f)

    # Parse activity entries from each file
    entries: list[dict[str, str]] = []
    for file_path in entity_files:
        # Determine entity type from path
        rel = file_path.relative_to(repo_root).as_posix()
        if file_path.name == "PROJECT.md":
            etype = "project"
        elif file_path.name == "EPIC.md":
            etype = "epic"
        elif "/tasks/" in rel:
            etype = "task"
        elif "/issues/" in rel:
            etype = "issue"
        elif "/milestones/" in rel:
            etype = "milestone"
        elif "/inbox/" in rel:
            etype = "inbox"
        elif "/specs/" in rel:
            etype = "spec"
        elif "/plans/" in rel:
            etype = "plan"
        else:
            etype = "unknown"

        # Apply entity type filter
        if entity_type and etype != entity_type:
            continue

        # Get entity title/ID from frontmatter (first line after ---)
        entity_id = file_path.stem
        entity_title = file_path.stem

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Try to get title from frontmatter
        fm_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        if fm_match:
            entity_title = fm_match.group(1).strip().strip('"').strip("'")
        id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
        if id_match:
            entity_id = id_match.group(1).strip().strip('"').strip("'")

        # Find activity section
        activity_section = ""
        in_activity = False
        for line in content.split("\n"):
            if line.strip() == "## Activity Log":
                in_activity = True
                continue
            if in_activity:
                if line.startswith("## "):
                    break
                activity_section += line + "\n"

        if not activity_section:
            continue

        for match in ACTIVITY_ENTRY_RE.finditer(activity_section):
            entry_date = match.group("date")
            action = match.group("action").strip()
            entry_actor = match.group("actor").strip()
            note = match.group("note") or ""

            # Apply filters
            if actor and entry_actor != actor:
                continue
            if since and entry_date < since:
                continue

            entries.append({
                "date": entry_date,
                "action": action,
                "actor": entry_actor,
                "note": note.strip(),
                "entity_type": etype,
                "entity_id": entity_id,
                "entity_title": entity_title,
                "path": rel,
            })

    # Sort by date descending, then by entity
    entries.sort(key=lambda e: (e["date"], e["entity_id"]), reverse=True)
    return entries[:limit]
