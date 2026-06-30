from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.resolver import resolve_entity
from trailmind.roster import Roster
from trailmind.task_status import TASK_STATUSES, validate_task_status, validate_task_transition


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _missing_epic(raw: str) -> TrailmindError:
    return TrailmindError(f"epic {raw} does not exist")


def _resolve_epic(repo_root: Path, raw: str) -> Path:
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

    if not (candidate / "EPIC.md").is_file():
        raise _missing_epic(raw)
    return candidate


def _initial_body(title: str, filer: str) -> str:
    today = date.today().isoformat()
    return (
        f"# {title}\n\n"
        "## Scope\n\n"
        "TBD\n\n"
        "## Acceptance\n\n"
        "- TBD\n\n"
        "## Activity Log\n\n"
        f"- {today}: Created task by {filer}.\n"
    )


def _ensure_tasks_directory(tasks_path: Path) -> None:
    if tasks_path.exists() and not tasks_path.is_dir():
        raise TrailmindError(f"tasks path {tasks_path} is not a directory")
    tasks_path.mkdir(parents=True, exist_ok=True)


def add_task(
    repo_root: Path,
    *,
    epic: str,
    filer: str,
    owner: str,
    title: str,
    code_paths: list[str],
    design_doc: str | None,
    depends_on: list[str],
    soft_depends_on: list[str],
    known_issues: list[str],
) -> Path:
    epic_path = _resolve_epic(repo_root, epic)
    roster = Roster.load(repo_root / "roster.yaml")
    filer_shortname = roster.require_shortname(filer)
    filer_uid = roster.require_uid(filer)
    owner_shortname = roster.require_shortname(owner)

    tasks_path = epic_path / "tasks"
    _ensure_tasks_directory(tasks_path)
    task_id = next_entity_id(tasks_path, entity="T", uid=filer_uid)
    task_path = tasks_path / f"{task_id}-{slugify(title)}.md"
    write_entity(
        task_path,
        frontmatter={
            "id": task_id,
            "title": title,
            "filer": filer_shortname,
            "owner": owner_shortname,
            "status": "created",
            "created": date.today().isoformat(),
            "start": None,
            "due": None,
            "branches": {},
            "verify": {},
            "code_paths": code_paths,
            "design_doc": design_doc,
            "depends_on": depends_on,
            "soft_depends_on": soft_depends_on,
            "known_issues": known_issues,
        },
        body=_initial_body(title, filer_shortname),
    )
    return task_path


def set_task_status(
    repo_root: Path,
    *,
    task_ref: str,
    status: str,
    actor: str,
    note: str | None = None,
) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    current_status, target_status = validate_task_transition(frontmatter.get("status", "created"), status)
    frontmatter["status"] = target_status
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Status changed from {current_status} to {target_status}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def update_task_status(repo_root: Path, *, task_ref: str, status: str) -> Path:
    status = validate_task_status(status)
    return set_task_status(repo_root, task_ref=task_ref, status=status, actor="trailmind")


def close_task(repo_root: Path, *, task_ref: str, closer: str, note: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    frontmatter["status"] = "done"
    body = append_activity_entry(
        body,
        action_activity_entry(action="Closed", actor_label="closer", actor=closer, note=note),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path
