from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.resolver import resolve_entity
from trailmind.roster import Roster
from trailmind.task_rules import (
    assert_deliverables_gate,
    assert_dependency_gate,
    format_soft_dependency_warning,
    normalize_deliverable_item,
    soft_dependency_warnings,
    string_list_field,
)
from trailmind.task_status import (
    STATUS_NORMALIZATIONS,
    is_terminal_task_status,
    normalize_task_status,
    validate_task_status,
    validate_task_transition,
)


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_deliverable_items(items: list[str]) -> list[str]:
    return [item for item in (normalize_deliverable_item(item) for item in items) if item]


TASK_PRIORITIES = ("low", "medium", "high", "critical")
DEFAULT_PRIORITY = "medium"


def validate_task_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized not in TASK_PRIORITIES:
        expected = ", ".join(TASK_PRIORITIES)
        raise TrailmindError(f"invalid task priority {priority!r}; expected one of: {expected}")
    return normalized


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


@dataclass(frozen=True)
class StatusNormalization:
    path: Path
    task_id: str
    old_status: str
    new_status: str
    changed: bool


@dataclass(frozen=True)
class _PendingStatusNormalization:
    result: StatusNormalization
    frontmatter: dict[str, Any]
    body: str


def _iter_task_files(repo_root: Path) -> list[Path]:
    projects_path = repo_root / "projects"
    if not projects_path.exists():
        return []
    return sorted(path for path in projects_path.glob("*/*/tasks/T-*.md") if path.is_file())


def normalize_task_statuses(repo_root: Path, *, write: bool) -> list[StatusNormalization]:
    normalizations: list[StatusNormalization] = []
    pending_writes: list[_PendingStatusNormalization] = []
    for task_path in _iter_task_files(repo_root):
        frontmatter, body = read_entity_user_facing(task_path, label="task")
        old_status = str(frontmatter.get("status", "created")).strip()
        if old_status not in STATUS_NORMALIZATIONS:
            normalize_task_status(old_status)
            continue
        new_status = normalize_task_status(old_status)
        task_id = str(frontmatter.get("id") or task_path.stem)
        result = StatusNormalization(
            path=task_path,
            task_id=task_id,
            old_status=old_status,
            new_status=new_status,
            changed=write,
        )
        normalizations.append(result)
        pending_writes.append(_PendingStatusNormalization(result=result, frontmatter=frontmatter, body=body))

    if write:
        for item in pending_writes:
            item.frontmatter["status"] = item.result.new_status
            write_entity(item.result.path, frontmatter=item.frontmatter, body=item.body)
    return normalizations


def list_tasks(
    repo_root: Path,
    *,
    epic_ref: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    overdue: bool = False,
) -> list[dict[str, Any]]:
    """List tasks in an epic or across the repo, with optional filtering."""
    from datetime import date
    from trailmind.scopes import resolve_epic_dir

    if epic_ref:
        epic_path = resolve_epic_dir(repo_root, epic_ref)
        task_paths = sorted(epic_path.glob("tasks/T-*.md"))
    else:
        task_paths = _iter_task_files(repo_root)

    today = date.today().isoformat()
    tasks = []
    for path in task_paths:
        if not path.is_file():
            continue
        try:
            frontmatter, _body = read_entity_user_facing(path, label="task")
        except TrailmindError:
            continue

        task_status = str(frontmatter.get("status") or "created")
        task_owner = str(frontmatter.get("owner") or "")
        task_priority = str(frontmatter.get("priority") or "")
        task_due = frontmatter.get("due")

        # Apply filters
        if status and task_status != status:
            continue
        if owner and task_owner != owner:
            continue
        if priority and task_priority != priority:
            continue
        if due_before and (not task_due or task_due > due_before):
            continue
        if due_after and (not task_due or task_due < due_after):
            continue
        if overdue and (not task_due or task_due >= today or task_status in ("done", "wontfix")):
            continue

        tasks.append({
            "id": str(frontmatter.get("id") or path.stem),
            "title": str(frontmatter.get("title") or path.stem),
            "status": task_status,
            "owner": task_owner,
            "priority": task_priority,
            "due": str(task_due) if task_due else "",
            "filer": str(frontmatter.get("filer") or ""),
            "created": str(frontmatter.get("created") or ""),
            "path": path.relative_to(repo_root).as_posix(),
        })
    return tasks


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "": 4}


def next_tasks(
    repo_root: Path,
    *,
    owner: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the most actionable tasks, sorted by priority then due date.

    Includes tasks in `ready` or `created` status (not done, wontfix, blocked, or in_progress).
    Sorted by: priority (critical first), then due date (earliest first), then created date.
    """
    ready = list_tasks(repo_root, status="ready", owner=owner)
    created = list_tasks(repo_root, status="created", owner=owner)
    candidates = ready + created

    # Also include in_progress tasks that might need attention
    in_progress = list_tasks(repo_root, status="in_progress", owner=owner)
    # Mark in_progress tasks for display
    for t in in_progress:
        t["_in_progress"] = True
    candidates = in_progress + candidates

    def sort_key(t: dict[str, Any]) -> tuple:
        pri = PRIORITY_ORDER.get(t.get("priority", ""), 4)
        due = t.get("due", "") or "9999-99-99"  # no due date = last
        created = t.get("created", "") or "9999-99-99"
        in_prog = 0 if t.get("_in_progress") else 1  # in_progress first
        return (in_prog, pri, due, created)

    candidates.sort(key=sort_key)
    return candidates[:limit]


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
    deliverables: list[str],
    priority: str = DEFAULT_PRIORITY,
) -> Path:
    epic_path = _resolve_epic(repo_root, epic)
    roster = Roster.load(repo_root / "roster.yaml")
    filer_shortname = roster.require_shortname(filer)
    filer_uid = roster.require_uid(filer)
    owner_shortname = roster.require_shortname(owner)
    normalized_deliverables = _normalize_deliverable_items(deliverables)
    validated_priority = validate_task_priority(priority)

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
            "priority": validated_priority,
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
            "deliverables": normalized_deliverables,
            "completed_deliverables": [],
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
) -> tuple[Path, str | None]:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    current_status, target_status = validate_task_transition(frontmatter.get("status", "created"), status)
    assert_dependency_gate(repo_root, frontmatter, target_status=target_status)
    assert_deliverables_gate(frontmatter, target_status=target_status)
    warning = format_soft_dependency_warning(soft_dependency_warnings(repo_root, frontmatter))
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
    return task_path, warning


def update_task_status(repo_root: Path, *, task_ref: str, status: str) -> Path:
    status = validate_task_status(status)
    path, _warning = set_task_status(repo_root, task_ref=task_ref, status=status, actor="trailmind")
    return path


def set_task_priority(
    repo_root: Path,
    *,
    task_ref: str,
    priority: str,
    actor: str,
    note: str | None = None,
) -> Path:
    validated_priority = validate_task_priority(priority)
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    old_priority = str(frontmatter.get("priority", DEFAULT_PRIORITY))
    frontmatter["priority"] = validated_priority
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Priority changed from {old_priority} to {validated_priority}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def set_task_due(
    repo_root: Path,
    *,
    task_ref: str,
    due_date: str | None,
    actor: str,
    note: str | None = None,
) -> Path:
    """Set or clear a task's due date.

    Pass due_date=None to clear the due date.
    """
    if due_date is not None:
        from datetime import datetime
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError as exc:
            raise TrailmindError(f"invalid due date {due_date!r}; expected YYYY-MM-DD") from exc

    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    old_due = frontmatter.get("due")
    frontmatter["due"] = due_date

    if due_date is None:
        action = f"Cleared due date (was {old_due})" if old_due else "Cleared due date"
    else:
        action = f"Due date set to {due_date}" + (f" (was {old_due})" if old_due else "")

    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def start_task(
    repo_root: Path,
    *,
    task_ref: str,
    actor: str,
    note: str | None = None,
) -> tuple[Path, str | None]:
    """Mark a task as in_progress and set the start date to today."""
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")

    # Set start date if not already set
    if not frontmatter.get("start"):
        frontmatter["start"] = date.today().isoformat()

    path, warning = set_task_status(
        repo_root,
        task_ref=task_ref,
        status="in_progress",
        actor=actor,
        note=note,
    )
    # Re-read to get the updated frontmatter, then write start date
    fm2, body2 = read_entity_user_facing(path, label="task")
    if not fm2.get("start"):
        fm2["start"] = date.today().isoformat()
        write_entity(path, frontmatter=fm2, body=body2)
    return path, warning


def complete_task(
    repo_root: Path,
    *,
    task_ref: str,
    actor: str,
    note: str | None = None,
) -> tuple[Path, str | None]:
    """Mark a task as done.

    If the task is in 'created' status, transitions to 'ready' first since
    'created' → 'done' is not a valid direct transition.
    """
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, _body = read_entity_user_facing(task_path, label="task")
    current = str(frontmatter.get("status", "created"))

    if current == "created":
        set_task_status(repo_root, task_ref=task_ref, status="ready", actor=actor, note=None)

    return set_task_status(
        repo_root,
        task_ref=task_ref,
        status="done",
        actor=actor,
        note=note,
    )


def add_task_dependency(
    repo_root: Path,
    *,
    task_ref: str,
    depends_on_ref: str,
    actor: str,
    soft: bool = False,
    note: str | None = None,
) -> Path:
    """Add a dependency to a task.

    If soft=True, adds to soft_depends_on instead of depends_on.
    """
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    dep_path = resolve_entity(repo_root, raw=depends_on_ref, entity="T")

    if task_path == dep_path:
        raise TrailmindError("task cannot depend on itself")

    frontmatter, body = read_entity_user_facing(task_path, label="task")
    field = "soft_depends_on" if soft else "depends_on"
    label = "soft dependency" if soft else "dependency"

    existing = string_list_field(frontmatter, field, label="task")
    dep_id = str(read_entity_user_facing(dep_path, label="task")[0].get("id") or dep_path.stem)

    if dep_id in existing:
        raise TrailmindError(f"task already has {label} on {dep_id}")

    existing.append(dep_id)
    frontmatter[field] = existing

    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Added {label}: depends on {dep_id}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def remove_task_dependency(
    repo_root: Path,
    *,
    task_ref: str,
    depends_on_ref: str,
    actor: str,
    soft: bool = False,
    note: str | None = None,
) -> Path:
    """Remove a dependency from a task."""
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    field = "soft_depends_on" if soft else "depends_on"
    label = "soft dependency" if soft else "dependency"

    existing = string_list_field(frontmatter, field, label="task")
    dep_id = depends_on_ref.strip()

    if dep_id not in existing:
        raise TrailmindError(f"task does not have {label} on {dep_id}")

    existing.remove(dep_id)
    frontmatter[field] = existing

    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Removed {label}: no longer depends on {dep_id}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def edit_task(
    repo_root: Path,
    *,
    task_ref: str,
    actor: str,
    title: str | None = None,
    code_paths: list[str] | None = None,
    design_doc: str | None = None,
    note: str | None = None,
) -> Path:
    """Edit editable fields on a task.

    Only provided fields are updated. None means "don't change".
    """
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")

    changes: list[str] = []

    if title is not None and title.strip():
        old_title = str(frontmatter.get("title", ""))
        frontmatter["title"] = title.strip()
        changes.append(f"Title: {old_title} → {title.strip()}")

    if code_paths is not None:
        old_paths = string_list_field(frontmatter, "code_paths", label="task")
        frontmatter["code_paths"] = [p.strip() for p in code_paths if p.strip()]
        changes.append(f"Code paths: {', '.join(old_paths) or '(none)'} → {', '.join(frontmatter['code_paths']) or '(none)'}")

    if design_doc is not None:
        old_doc = str(frontmatter.get("design_doc", "") or "")
        new_doc = design_doc.strip() or None
        frontmatter["design_doc"] = new_doc
        changes.append(f"Design doc: {old_doc or '(none)'} → {new_doc or '(none)'}")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title, --code-paths, or --design-doc")

    action = f"Edited task: {'; '.join(changes)}"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def add_task_deliverable(repo_root: Path, *, task_ref: str, item: str, actor: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    deliverable = normalize_deliverable_item(item)
    if not deliverable:
        raise TrailmindError("deliverable item is required")
    status = normalize_task_status(frontmatter.get("status", "created"))
    if is_terminal_task_status(status):
        raise TrailmindError(f"cannot add deliverable to {status} task")
    deliverables = _normalize_deliverable_items(string_list_field(frontmatter, "deliverables", label="task"))
    if deliverable not in deliverables:
        deliverables.append(deliverable)
    frontmatter["deliverables"] = deliverables
    frontmatter["completed_deliverables"] = _normalize_deliverable_items(
        string_list_field(frontmatter, "completed_deliverables", label="task")
    )
    body = append_activity_entry(
        body,
        action_activity_entry(action="Added deliverable", actor_label="actor", actor=actor, note=deliverable),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def complete_task_deliverable(repo_root: Path, *, task_ref: str, item: str, actor: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    deliverable = normalize_deliverable_item(item)
    if not deliverable:
        raise TrailmindError("deliverable item is required")
    deliverables = _normalize_deliverable_items(string_list_field(frontmatter, "deliverables", label="task"))
    if deliverable not in deliverables:
        raise TrailmindError(f"deliverable {deliverable!r} is not defined on task")
    completed = _normalize_deliverable_items(string_list_field(frontmatter, "completed_deliverables", label="task"))
    if deliverable not in completed:
        completed.append(deliverable)
    frontmatter["deliverables"] = deliverables
    frontmatter["completed_deliverables"] = completed
    body = append_activity_entry(
        body,
        action_activity_entry(action="Completed deliverable", actor_label="actor", actor=actor, note=deliverable),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def assign_task(
    repo_root: Path,
    *,
    task_ref: str,
    owner: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Reassign a task to a different owner."""
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")

    roster = Roster.load(repo_root / "roster.yaml")
    new_owner = roster.resolve_shortname(owner)
    old_owner = str(frontmatter.get("owner", "unknown"))

    frontmatter["owner"] = new_owner
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Assigned to {new_owner} (was {old_owner})",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def close_task(repo_root: Path, *, task_ref: str, closer: str, note: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    _current_status, target_status = validate_task_transition(
        frontmatter.get("status", "created"),
        "done",
    )
    assert_dependency_gate(repo_root, frontmatter, target_status="done")
    assert_deliverables_gate(frontmatter, target_status="done")
    frontmatter["status"] = target_status
    body = append_activity_entry(
        body,
        action_activity_entry(action="Closed", actor_label="closer", actor=closer, note=note),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path
