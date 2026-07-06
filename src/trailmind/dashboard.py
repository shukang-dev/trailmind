from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jinja2 import Environment, FileSystemLoader

from trailmind.entity_io import EntityFormatError, read_entity
from trailmind.errors import TrailmindError
from trailmind.paths import validate_path_component


_ENTITY_FILENAME_RE = {
    "task": re.compile(r"^T-\d{6}-\d{3,}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$"),
    "issue": re.compile(r"^I-\d{6}-\d{3,}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$"),
    "milestone": re.compile(r"^M-\d{3,}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$"),
}


def render_overview(repo_root: Path) -> Path:
    projects = [_project_summary(repo_root, project_path) for project_path in _project_dirs(repo_root)]

    # Compute aggregates across all epics
    all_epics: list[dict[str, Any]] = []
    for project in projects:
        all_epics.extend(project.get("epics", []))

    # For aggregates we need child counts; re-read epics with include_children
    total_tasks = 0
    total_issues = 0
    total_specs = 0
    total_plans = 0
    total_milestones = 0
    overdue_tasks = 0
    today_str = date.today().isoformat()
    task_status_counter: Counter[str] = Counter()
    task_priority_counter: Counter[str] = Counter()

    for project in projects:
        for epic_data in project.get("epics", []):
            epic_path = repo_root / epic_data["relative_path"]
            epic_full = _epic_summary(repo_root, epic_path, include_children=True)
            total_tasks += epic_full.get("task_count", 0)
            total_issues += epic_full.get("issue_count", 0)
            total_specs += epic_full.get("spec_count", 0)
            total_plans += epic_full.get("plan_count", 0)
            total_milestones += epic_full.get("milestone_count", 0)
            for task in epic_full.get("tasks", []):
                status = task.get("status", "unknown")
                task_status_counter[status] += 1
                priority = task.get("priority", "")
                if priority:
                    task_priority_counter[priority] += 1
                due = task.get("due", "")
                if due and due < today_str and status not in ("done", "wontfix"):
                    overdue_tasks += 1

    output_path = repo_root / "overview.html"
    return _render_to_file(
        "overview.html.j2",
        output_path,
        {
            "title": "Trailmind Overview",
            "repo_name": repo_root.name,
            "projects": projects,
            "project_count": len(projects),
            "epic_count": sum(project["epic_count"] for project in projects),
            "total_tasks": total_tasks,
            "total_issues": total_issues,
            "total_specs": total_specs,
            "total_plans": total_plans,
            "total_milestones": total_milestones,
            "overdue_tasks": overdue_tasks,
            "task_status_counts": dict(task_status_counter),
            "task_priority_counts": dict(task_priority_counter),
        },
    )


def render_project_dashboard(repo_root: Path, project: str) -> Path:
    project_path = _resolve_project_dir(repo_root, project)
    return render_project_dashboard_at(repo_root, project_path)


def render_project_dashboard_at(repo_root: Path, project_path: Path) -> Path:
    project_path = _require_project_dir(repo_root, project_path)
    project = _project_summary(repo_root, project_path)
    output_path = project_path / "dashboard.html"
    return _render_to_file(
        "project-dashboard.html.j2",
        output_path,
        {
            "title": f"{project['title']} Dashboard",
            "project": project,
            "epics": project["epics"],
        },
    )


def render_epic_dashboard(repo_root: Path, epic: str) -> Path:
    epic_path = _resolve_epic_dir(repo_root, epic)
    return render_epic_dashboard_at(repo_root, epic_path)


def render_epic_dashboard_at(repo_root: Path, epic_path: Path) -> Path:
    epic_path = _require_epic_dir(repo_root, epic_path)
    epic = _epic_summary(repo_root, epic_path, include_children=True)
    output_path = epic_path / "dashboard.html"
    return _render_to_file(
        "epic-dashboard.html.j2",
        output_path,
        {
            "title": f"{epic['title']} Dashboard",
            "epic": epic,
            "today": date.today().isoformat(),
        },
    )


def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render_to_file(template_name: str, output_path: Path, context: dict[str, Any]) -> Path:
    html = _template_env().get_template(template_name).render(**context)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _project_dirs(repo_root: Path) -> list[Path]:
    projects_path = repo_root / "projects"
    if not projects_path.exists():
        return []
    if not projects_path.is_dir():
        raise TrailmindError(f"projects path {projects_path} is not a directory")
    return sorted(path for path in projects_path.iterdir() if (path / "PROJECT.md").is_file())


def _epic_dirs(project_path: Path) -> list[Path]:
    return sorted(path for path in project_path.iterdir() if path.is_dir() and (path / "EPIC.md").is_file())


def _resolve_project_dir(repo_root: Path, raw: str) -> Path:
    try:
        project = validate_path_component(raw, "project")
    except TrailmindError as exc:
        raise _missing_project(raw) from exc
    return _require_project_dir(repo_root, repo_root / "projects" / project, label=raw)


def _resolve_epic_dir(repo_root: Path, raw: str) -> Path:
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in posix_path.parts
        or ".." in windows_path.parts
        or len(posix_path.parts) != 3
        or posix_path.parts[0] != "projects"
    ):
        raise _missing_epic(raw)

    candidate = repo_root / Path(*posix_path.parts)
    try:
        candidate.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise _missing_epic(raw) from exc
    return _require_epic_dir(repo_root, candidate, label=raw)


def _require_project_dir(repo_root: Path, project_path: Path, *, label: str | None = None) -> Path:
    try:
        project_path.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise _missing_project(label or project_path.name) from exc
    if not (project_path / "PROJECT.md").is_file():
        raise _missing_project(label or project_path.name)
    return project_path


def _require_epic_dir(repo_root: Path, epic_path: Path, *, label: str | None = None) -> Path:
    try:
        epic_path.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise _missing_epic(label or _relative(repo_root, epic_path)) from exc
    if not (epic_path / "EPIC.md").is_file():
        raise _missing_epic(label or _relative(repo_root, epic_path))
    return epic_path


def _missing_project(raw: str) -> TrailmindError:
    return TrailmindError(f"project {raw} does not exist")


def _missing_epic(raw: str) -> TrailmindError:
    return TrailmindError(f"epic {raw} does not exist")


def _read_entity_user_facing(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        return read_entity(path)
    except EntityFormatError as exc:
        raise TrailmindError(str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise TrailmindError(f"could not read {label} file {path}: file must be valid UTF-8") from exc
    except OSError as exc:
        raise TrailmindError(f"could not read {label} file {path}: {exc}") from exc


def _project_summary(repo_root: Path, project_path: Path) -> dict[str, Any]:
    frontmatter, body = _read_entity_user_facing(project_path / "PROJECT.md", label="project")
    epics = [_epic_summary(repo_root, epic_path, include_children=False) for epic_path in _epic_dirs(project_path)]
    return {
        "path": project_path,
        "relative_path": _relative(repo_root, project_path),
        "slug": _string_value(frontmatter.get("slug"), project_path.name),
        "title": _string_value(frontmatter.get("title"), project_path.name),
        "goal": _string_value(frontmatter.get("goal"), ""),
        "owners": _string_list(frontmatter.get("owners")),
        "tags": _string_list(frontmatter.get("tags")),
        "created": _string_value(frontmatter.get("created"), ""),
        "body": body.strip(),
        "epics": epics,
        "epic_count": len(epics),
        "epic_state_counts": _status_counts(epics, "state"),
    }


def _epic_summary(repo_root: Path, epic_path: Path, *, include_children: bool) -> dict[str, Any]:
    frontmatter, body = _read_entity_user_facing(epic_path / "EPIC.md", label="epic")
    epic: dict[str, Any] = {
        "path": epic_path,
        "relative_path": _relative(repo_root, epic_path),
        "slug": _string_value(frontmatter.get("slug"), epic_path.name),
        "title": _string_value(frontmatter.get("title"), epic_path.name),
        "project": _string_value(frontmatter.get("project"), epic_path.parent.name),
        "goal": _string_value(frontmatter.get("goal"), ""),
        "state": _string_value(frontmatter.get("state"), "unknown"),
        "start": _string_value(frontmatter.get("start"), ""),
        "target": _string_value(frontmatter.get("target"), ""),
        "roster": _string_list(frontmatter.get("roster")),
        "repos": _string_list(frontmatter.get("repos")),
        "created": _string_value(frontmatter.get("created"), ""),
        "body": body.strip(),
    }
    if include_children:
        tasks = _entity_summaries(repo_root, epic_path / "tasks", label="task")
        issues = _entity_summaries(repo_root, epic_path / "issues", label="issue")
        milestones = _entity_summaries(repo_root, epic_path / "milestones", label="milestone")
        specs = _doc_summaries(repo_root, epic_path / "docs" / "specs", label="spec")
        plans = _doc_summaries(repo_root, epic_path / "docs" / "plans", label="plan")
        epic.update(
            {
                "tasks": tasks,
                "issues": issues,
                "milestones": milestones,
                "specs": specs,
                "plans": plans,
                "task_count": len(tasks),
                "issue_count": len(issues),
                "milestone_count": len(milestones),
                "spec_count": len(specs),
                "plan_count": len(plans),
                "task_status_counts": _status_counts(tasks, "status"),
                "issue_status_counts": _status_counts(issues, "status"),
                "milestone_status_counts": _status_counts(milestones, "status"),
                "spec_status_counts": _status_counts(specs, "status"),
                "plan_status_counts": _status_counts(plans, "status"),
            }
        )
    else:
        epic.update(
            {
                "task_count": _markdown_count(epic_path / "tasks", label="task"),
                "issue_count": _markdown_count(epic_path / "issues", label="issue"),
                "milestone_count": _markdown_count(epic_path / "milestones", label="milestone"),
                "spec_count": _doc_count(epic_path / "docs" / "specs"),
                "plan_count": _doc_count(epic_path / "docs" / "plans"),
            }
        )
    return epic


def _entity_summaries(repo_root: Path, directory: Path, *, label: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise TrailmindError(f"{label}s path {directory} is not a directory")
    entities = []
    for path in _entity_markdown_files(directory, label=label):
        frontmatter, body = _read_entity_user_facing(path, label=label)
        entities.append(
            {
                "path": path,
                "relative_path": _relative(repo_root, path),
                "id": _string_value(frontmatter.get("id"), path.stem),
                "title": _string_value(frontmatter.get("title"), path.stem),
                "status": _string_value(frontmatter.get("status"), "unknown"),
                "owner": _string_value(frontmatter.get("owner"), ""),
                "filer": _string_value(frontmatter.get("filer"), ""),
                "severity": _string_value(frontmatter.get("severity"), ""),
                "priority": _string_value(frontmatter.get("priority"), ""),
                "due": _string_value(frontmatter.get("due"), ""),
                "date": _string_value(frontmatter.get("date"), ""),
                "created": _string_value(frontmatter.get("created"), ""),
                "body": body.strip(),
            }
        )
    return entities


def _entity_markdown_files(directory: Path, *, label: str) -> list[Path]:
    filename_re = _ENTITY_FILENAME_RE[label]
    return sorted(
        path
        for path in directory.glob("*.md")
        if path.is_file() and filename_re.fullmatch(path.stem)
    )


def _markdown_count(directory: Path, *, label: str) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    return len(_entity_markdown_files(directory, label=label))


def _doc_summaries(repo_root: Path, directory: Path, *, label: str) -> list[dict[str, Any]]:
    """Summarize Markdown docs (specs, plans) by frontmatter."""
    if not directory.exists() or not directory.is_dir():
        return []
    docs = []
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        try:
            frontmatter, body = _read_entity_user_facing(path, label=label)
        except TrailmindError:
            continue
        docs.append(
            {
                "path": path,
                "relative_path": _relative(repo_root, path),
                "title": _string_value(frontmatter.get("title"), path.stem),
                "status": _string_value(frontmatter.get("status"), "unknown"),
                "scope": _string_value(frontmatter.get("scope"), ""),
                "created": _string_value(frontmatter.get("created"), ""),
                "linked_spec": _string_value(frontmatter.get("linked_spec"), ""),
                "linked_plans": _string_list(frontmatter.get("linked_plans")),
                "generated_tasks": _string_list(frontmatter.get("generated_tasks")),
                "body": body.strip(),
            }
        )
    return docs


def _doc_count(directory: Path) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    return sum(1 for p in directory.glob("*.md") if p.is_file())


def _status_counts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(_string_value(item.get(key), "unknown") or "unknown" for item in items)
    return [{"label": label, "count": counts[label]} for label in sorted(counts)]


def _string_value(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_string_value(item, "") for item in value]
    return [_string_value(value, "")]


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
