from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError


def import_repo(repo_root: Path, data: dict[str, Any], *, force: bool = False) -> list[Path]:
    """Import project data from a JSON export into the repo.

    Returns list of created/modified file paths.
    """
    created: list[Path] = []

    # Import roster
    roster_data = data.get("roster", [])
    if roster_data:
        created.extend(_import_roster(repo_root, roster_data, force=force))

    # Import projects
    for project_data in data.get("projects", []):
        created.extend(_import_project(repo_root, project_data, force=force))

    return created


def _import_roster(repo_root: Path, developers: list[dict[str, Any]], *, force: bool) -> list[Path]:
    import yaml

    roster_path = repo_root / "roster.yaml"
    if roster_path.exists() and not force:
        existing = yaml.safe_load(roster_path.read_text(encoding="utf-8")) or {}
        existing_devs = existing.get("developers", [])
        existing_emails = {d.get("email") for d in existing_devs if isinstance(d, dict)}
        new_devs = [d for d in developers if d.get("email") not in existing_emails]
        if not new_devs:
            return []
        existing["developers"] = existing_devs + new_devs
    else:
        existing = {"developers": developers}

    roster_path.parent.mkdir(parents=True, exist_ok=True)
    roster_path.write_text(
        yaml.safe_dump(existing, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return [roster_path]


def _import_project(repo_root: Path, project: dict[str, Any], *, force: bool) -> list[Path]:
    created: list[Path] = []
    slug = project.get("slug", "unknown")
    project_path = repo_root / "projects" / slug
    project_path.mkdir(parents=True, exist_ok=True)

    # PROJECT.md
    project_md = project_path / "PROJECT.md"
    if not project_md.exists() or force:
        fm = {
            "slug": project.get("slug", ""),
            "title": project.get("title", ""),
            "goal": project.get("goal", ""),
            "state": project.get("state", "unknown"),
            "owners": project.get("owners", []),
            "tags": project.get("tags", []),
            "created": project.get("created", ""),
        }
        body = project.get("body", "")
        if not body:
            body = f"# {project.get('title', slug)}\n\n"
        write_entity(project_md, frontmatter=fm, body=body)
        created.append(project_md)

    # Project-level inbox
    for item in project.get("inbox", []):
        created.extend(_import_inbox_item(repo_root, project_path, item, force=force))

    # Epics
    for epic_data in project.get("epics", []):
        created.extend(_import_epic(repo_root, project_path, epic_data, force=force))

    return created


def _import_epic(
    repo_root: Path,
    project_path: Path,
    epic: dict[str, Any],
    *,
    force: bool,
) -> list[Path]:
    created: list[Path] = []
    slug = epic.get("slug", "unknown")
    epic_path = project_path / slug
    epic_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    for subdir in ("tasks", "issues", "milestones", "inbox", "docs/specs", "docs/plans"):
        (epic_path / subdir).mkdir(parents=True, exist_ok=True)

    # EPIC.md
    epic_md = epic_path / "EPIC.md"
    if not epic_md.exists() or force:
        fm = {
            "slug": epic.get("slug", ""),
            "title": epic.get("title", ""),
            "project": project_path.name,
            "goal": epic.get("goal", ""),
            "state": epic.get("state", "unknown"),
            "start": epic.get("start", ""),
            "target": epic.get("target", ""),
            "roster": epic.get("roster", []),
            "repos": epic.get("repos", []),
            "created": epic.get("created", ""),
            "carried_issues": [],
        }
        body = epic.get("body", "")
        if not body:
            body = f"# {epic.get('title', slug)}\n\n"
        write_entity(epic_md, frontmatter=fm, body=body)
        created.append(epic_md)

    # Tasks
    for task_data in epic.get("tasks", []):
        path = _import_entity_file(
            epic_path / "tasks",
            task_data,
            default_prefix="T",
            force=force,
        )
        if path:
            created.append(path)

    # Issues
    for issue_data in epic.get("issues", []):
        path = _import_entity_file(
            epic_path / "issues",
            issue_data,
            default_prefix="I",
            force=force,
        )
        if path:
            created.append(path)

    # Milestones
    for ms_data in epic.get("milestones", []):
        path = _import_entity_file(
            epic_path / "milestones",
            ms_data,
            default_prefix="M",
            force=force,
        )
        if path:
            created.append(path)

    # Inbox
    for item in epic.get("inbox", []):
        created.extend(_import_inbox_item(repo_root, epic_path, item, force=force))

    return created


def _import_entity_file(
    directory: Path,
    entity: dict[str, Any],
    *,
    default_prefix: str,
    force: bool,
) -> Path | None:
    entity_id = entity.get("id", "")
    title = entity.get("title", "untitled")

    # Build filename
    from trailmind.ids import slugify

    safe_title = slugify(title)
    if entity_id:
        filename = f"{entity_id}-{safe_title}.md" if safe_title else f"{entity_id}.md"
    else:
        filename = f"{default_prefix}-{safe_title}.md"

    file_path = directory / filename
    if file_path.exists() and not force:
        return None

    directory.mkdir(parents=True, exist_ok=True)

    # Build frontmatter from entity data
    fm: dict[str, Any] = {
        "id": entity_id or "",
        "title": title,
        "status": entity.get("status", "created"),
        "created": entity.get("created", ""),
    }

    # Copy known optional fields
    for field in ("filer", "owner", "severity", "date", "design_doc"):
        if field in entity and entity[field]:
            fm[field] = entity[field]

    for field in ("code_paths", "depends_on", "soft_depends_on", "known_issues",
                   "deliverables", "completed_deliverables", "linked_tasks",
                   "carried_into"):
        if field in entity and isinstance(entity[field], list):
            fm[field] = entity[field]

    body = entity.get("body", "")
    if not body:
        body = f"# {title}\n\n"

    write_entity(file_path, frontmatter=fm, body=body)
    return file_path


def _import_inbox_item(
    repo_root: Path,
    scope_path: Path,
    item: dict[str, Any],
    *,
    force: bool,
) -> list[Path]:
    from trailmind.ids import slugify

    inbox_dir = scope_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    item_id = item.get("id", "")
    title = item.get("title", "untitled")
    safe_title = slugify(title)
    filename = f"{item_id}-{safe_title}.md" if safe_title and item_id else f"{item_id}.md"

    file_path = inbox_dir / filename
    if file_path.exists() and not force:
        return []

    fm = {
        "id": item_id or "",
        "title": title,
        "author": item.get("author", ""),
        "scope": item.get("scope", ""),
        "status": item.get("status", "open"),
        "created": item.get("created", ""),
        "resolved": item.get("resolved", None),
    }
    body = item.get("body", "")
    if not body:
        body = f"# {title}\n\n"

    write_entity(file_path, frontmatter=fm, body=body)
    return [file_path]


def load_export_file(path: Path) -> dict[str, Any]:
    """Load and parse a JSON export file."""
    if not path.exists():
        raise TrailmindError(f"export file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrailmindError(f"invalid JSON in export file: {exc}") from exc
