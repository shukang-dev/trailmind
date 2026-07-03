from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trailmind.log import read_entity_user_facing


def export_repo(repo_root: Path) -> dict[str, Any]:
    """Export all Trailmind data in a repo as structured JSON."""
    projects_path = repo_root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        return {"projects": [], "roster": _load_roster(repo_root)}

    projects: list[dict[str, Any]] = []
    for project_path in sorted(p for p in projects_path.iterdir() if (p / "PROJECT.md").is_file()):
        project_data = _export_project(repo_root, project_path)
        if project_data is not None:
            projects.append(project_data)

    return {
        "roster": _load_roster(repo_root),
        "projects": projects,
    }


def _load_roster(repo_root: Path) -> list[dict[str, str]]:
    roster_path = repo_root / "roster.yaml"
    if not roster_path.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []
        devs = data.get("developers", [])
        if not isinstance(devs, list):
            return []
        return devs
    except Exception:
        return []


def _export_project(repo_root: Path, project_path: Path) -> dict[str, Any] | None:
    try:
        fm, body = read_entity_user_facing(project_path / "PROJECT.md", label="project")
    except Exception:
        return None

    epics: list[dict[str, Any]] = []
    for epic_path in sorted(e for e in project_path.iterdir() if (e / "EPIC.md").is_file()):
        epic_data = _export_epic(repo_root, epic_path)
        if epic_data is not None:
            epics.append(epic_data)

    # Project-level inbox
    project_inbox = _export_inbox(repo_root, project_path / "inbox")

    return {
        "slug": str(fm.get("slug") or project_path.name),
        "title": str(fm.get("title") or project_path.name),
        "goal": str(fm.get("goal") or ""),
        "state": str(fm.get("state") or "unknown"),
        "owners": _string_list(fm.get("owners")),
        "tags": _string_list(fm.get("tags")),
        "created": str(fm.get("created") or ""),
        "path": str(project_path.relative_to(repo_root)),
        "body": body.strip(),
        "inbox": project_inbox,
        "epics": epics,
    }


def _export_epic(repo_root: Path, epic_path: Path) -> dict[str, Any] | None:
    try:
        fm, body = read_entity_user_facing(epic_path / "EPIC.md", label="epic")
    except Exception:
        return None

    return {
        "slug": str(fm.get("slug") or epic_path.name),
        "title": str(fm.get("title") or epic_path.name),
        "goal": str(fm.get("goal") or ""),
        "state": str(fm.get("state") or "unknown"),
        "start": str(fm.get("start") or ""),
        "target": str(fm.get("target") or ""),
        "roster": _string_list(fm.get("roster")),
        "repos": _string_list(fm.get("repos")),
        "created": str(fm.get("created") or ""),
        "path": str(epic_path.relative_to(repo_root)),
        "body": body.strip(),
        "tasks": _export_entities(repo_root, epic_path / "tasks", "T-*.md", "task"),
        "issues": _export_entities(repo_root, epic_path / "issues", "I-*.md", "issue"),
        "milestones": _export_entities(repo_root, epic_path / "milestones", "M-*.md", "milestone"),
        "inbox": _export_inbox(repo_root, epic_path / "inbox"),
    }


def _export_entities(
    repo_root: Path,
    directory: Path,
    glob: str,
    label: str,
) -> list[dict[str, Any]]:
    if not directory.exists() or not directory.is_dir():
        return []

    entities: list[dict[str, Any]] = []
    for path in sorted(directory.glob(glob)):
        if not path.is_file():
            continue
        try:
            fm, body = read_entity_user_facing(path, label=label)
        except Exception:
            continue
        entity: dict[str, Any] = {
            "id": str(fm.get("id") or path.stem),
            "title": str(fm.get("title") or path.stem),
            "status": str(fm.get("status") or "unknown"),
            "created": str(fm.get("created") or ""),
            "path": str(path.relative_to(repo_root)),
            "body": body.strip(),
        }
        # Add common optional fields
        for field in ("filer", "owner", "severity", "date", "design_doc"):
            value = fm.get(field)
            if value is not None:
                entity[field] = str(value)
        for field in ("code_paths", "depends_on", "soft_depends_on", "known_issues",
                       "deliverables", "completed_deliverables", "linked_tasks",
                       "carried_into", "branches", "verify"):
            value = fm.get(field)
            if isinstance(value, list):
                entity[field] = [str(v) for v in value]
        entities.append(entity)
    return entities


def _export_inbox(repo_root: Path, directory: Path) -> list[dict[str, Any]]:
    if not directory.exists() or not directory.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("IN-*.md")):
        if not path.is_file():
            continue
        try:
            fm, body = read_entity_user_facing(path, label="inbox")
        except Exception:
            continue
        items.append({
            "id": str(fm.get("id") or path.stem),
            "title": str(fm.get("title") or path.stem),
            "status": str(fm.get("status") or "open"),
            "author": str(fm.get("author") or ""),
            "scope": str(fm.get("scope") or ""),
            "created": str(fm.get("created") or ""),
            "resolved": str(fm.get("resolved") or ""),
            "path": str(path.relative_to(repo_root)),
            "body": body.strip(),
        })
    return items


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def format_export(data: dict[str, Any]) -> str:
    """Format exported data as pretty-printed JSON."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
