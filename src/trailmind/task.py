from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import EntityFormatError, read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify
from trailmind.resolver import resolve_entity
from trailmind.roster import Roster


TASK_STATUSES = ("planned", "in_progress", "integration", "blocked", "done")


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


def _read_entity_user_facing(path: Path) -> tuple[dict[str, object], str]:
    try:
        return read_entity(path)
    except EntityFormatError as exc:
        raise TrailmindError(str(exc)) from exc


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


def _activity_entry(action: str, actor: str, note: str | None = None) -> str:
    entry = f"- {date.today().isoformat()}: {action} by {actor}."
    if note:
        entry = f"{entry} {note}"
    return entry


def _append_activity_entry(body: str, entry: str) -> str:
    text = body.rstrip("\n")
    if not text:
        return f"## Activity Log\n\n{entry}\n"

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "## Activity Log":
            continue

        section_end = len(lines)
        for cursor in range(index + 1, len(lines)):
            if lines[cursor].startswith("## "):
                section_end = cursor
                break

        before = lines[:section_end]
        before.append(entry)
        after = lines[section_end:]
        if after:
            before.append("")
            before.extend(after)
        return "\n".join(before) + "\n"

    return f"{text}\n\n## Activity Log\n\n{entry}\n"


def _validate_status(status: str) -> str:
    if status not in TASK_STATUSES:
        expected = ", ".join(TASK_STATUSES)
        raise TrailmindError(f"invalid task status {status!r}; expected one of: {expected}")
    return status


def add_task(
    repo_root: Path,
    *,
    epic: str,
    filer: str,
    owner: str,
    title: str,
    code_paths: list[str],
    design_doc: str,
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
    task_id = next_entity_id(tasks_path, entity="T", uid=filer_uid)
    task_path = tasks_path / f"{task_id}-{slugify(title)}.md"
    write_entity(
        task_path,
        frontmatter={
            "id": task_id,
            "title": title,
            "filer": filer_shortname,
            "owner": owner_shortname,
            "status": "planned",
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


def update_task_status(repo_root: Path, *, task_ref: str, status: str) -> Path:
    status = _validate_status(status)
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = _read_entity_user_facing(task_path)
    frontmatter["status"] = status
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def close_task(repo_root: Path, *, task_ref: str, closer: str, note: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = _read_entity_user_facing(task_path)
    frontmatter["status"] = "done"
    body = _append_activity_entry(body, _activity_entry("Closed", closer, note))
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path
