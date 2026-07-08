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
    project_ref: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    overdue: bool = False,
    due_within_days: int | None = None,
    has_due: bool | None = None,
    tag: str | None = None,
    sort_by: str = "created",
) -> list[dict[str, Any]]:
    """List tasks in an epic, a project, or across the repo, with optional filtering and sorting.

    sort_by: "created" (default), "priority", "due", "status", "title"
    tag: filter by tag name (case-insensitive substring match)
    """
    from datetime import date
    from trailmind.scopes import resolve_epic_dir

    if epic_ref:
        epic_path = resolve_epic_dir(repo_root, epic_ref)
        task_paths = sorted(epic_path.glob("tasks/T-*.md"))
    elif project_ref:
        project_dir = repo_root / "projects" / project_ref
        if not project_dir.exists():
            from trailmind.errors import TrailmindError
            raise TrailmindError(f"project not found: {project_ref}")
        task_paths = sorted(project_dir.glob("*/tasks/T-*.md"))
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
        if due_within_days is not None and due_within_days >= 0:
            from datetime import timedelta
            if not task_due or task_status in ("done", "wontfix"):
                continue
            if due_within_days == 0:
                # Due today only
                if task_due != today:
                    continue
            else:
                cutoff = (date.today() + timedelta(days=due_within_days)).isoformat()
                if task_due > cutoff or task_due < today:
                    continue
        if has_due is True and not task_due:
            continue
        if has_due is False and task_due:
            continue
        if tag:
            task_tags = frontmatter.get("tags") or []
            if isinstance(task_tags, list):
                tag_lower = tag.lower()
                if not any(tag_lower in str(t).lower() for t in task_tags):
                    continue
            else:
                continue

        task_tags_list = frontmatter.get("tags") or []
        if not isinstance(task_tags_list, list):
            task_tags_list = []
        # Derive epic path from file location
        rel_path = path.relative_to(repo_root).as_posix()
        epic_path = "/".join(rel_path.split("/")[:3])  # projects/<project>/<epic>
        tasks.append({
            "id": str(frontmatter.get("id") or path.stem),
            "title": str(frontmatter.get("title") or path.stem),
            "status": task_status,
            "owner": task_owner,
            "priority": task_priority,
            "due": str(task_due) if task_due else "",
            "filer": str(frontmatter.get("filer") or ""),
            "created": str(frontmatter.get("created") or ""),
            "tags": [str(t) for t in task_tags_list],
            "deliverables": list(frontmatter.get("deliverables") or []),
            "completed_deliverables": list(frontmatter.get("completed_deliverables") or []),
            "depends_on": list(frontmatter.get("depends_on") or []),
            "soft_depends_on": list(frontmatter.get("soft_depends_on") or []),
            "epic": epic_path,
            "path": rel_path,
        })

    # Sort
    STATUS_ORDER = {"in_progress": 0, "ready": 1, "blocked": 2, "created": 3, "done": 4, "wontfix": 5}

    def sort_key(t: dict[str, Any]) -> tuple:
        if sort_by == "priority":
            return (PRIORITY_ORDER.get(t["priority"], 4), t.get("due", "") or "9999-99-99", t.get("created", ""))
        elif sort_by == "due":
            return (t.get("due", "") or "9999-99-99", PRIORITY_ORDER.get(t["priority"], 4))
        elif sort_by == "status":
            return (STATUS_ORDER.get(t["status"], 9), PRIORITY_ORDER.get(t["priority"], 4))
        elif sort_by == "title":
            return (t.get("title", "").lower(),)
        else:  # created
            return (t.get("created", "") or "9999-99-99", PRIORITY_ORDER.get(t["priority"], 4))

    tasks.sort(key=sort_key)
    return tasks


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "": 4}


def next_tasks(
    repo_root: Path,
    *,
    owner: str | None = None,
    epic: str | None = None,
    project: str | None = None,
    tag: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the most actionable tasks, sorted by priority then due date.

    Includes tasks in `ready` or `created` status (not done, wontfix, blocked, or in_progress).
    Sorted by: priority (critical first), then due date (earliest first), then created date.
    """
    ready = list_tasks(repo_root, status="ready", owner=owner, epic_ref=epic, project_ref=project, tag=tag)
    created = list_tasks(repo_root, status="created", owner=owner, epic_ref=epic, project_ref=project, tag=tag)
    candidates = ready + created

    # Also include in_progress tasks that might need attention
    in_progress = list_tasks(repo_root, status="in_progress", owner=owner, epic_ref=epic, project_ref=project, tag=tag)
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
    due: str | None = None,
    tags: list[str] | None = None,
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

    # Validate due date if provided
    validated_due = None
    if due:
        from datetime import date as _date
        try:
            _date.fromisoformat(due)
            validated_due = due
        except ValueError:
            raise TrailmindError(f"invalid due date {due!r}; expected YYYY-MM-DD")

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
            "due": validated_due,
            "branches": {},
            "verify": {},
            "code_paths": code_paths,
            "design_doc": design_doc,
            "depends_on": depends_on,
            "soft_depends_on": soft_depends_on,
            "known_issues": known_issues,
            "deliverables": normalized_deliverables,
            "completed_deliverables": [],
            "tags": tags or [],
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
    due: str | None = None,
    tags: list[str] | None = None,
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

    if due is not None:
        from datetime import date as _date
        if due.strip():
            try:
                _date.fromisoformat(due.strip())
                validated_due = due.strip()
            except ValueError:
                raise TrailmindError(f"invalid due date {due!r}; expected YYYY-MM-DD")
        else:
            validated_due = None
        old_due = str(frontmatter.get("due") or "")
        frontmatter["due"] = validated_due
        changes.append(f"Due: {old_due or '(none)'} → {validated_due or '(none)'}")

    if tags is not None:
        old_tags = string_list_field(frontmatter, "tags", label="task")
        normalized = [t.strip() for t in tags if t.strip()]
        frontmatter["tags"] = normalized
        changes.append(f"Tags: {', '.join(old_tags) or '(none)'} → {', '.join(normalized) or '(none)'}")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title, --code-paths, --design-doc, --due, or --tags")

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


def move_task(
    repo_root: Path,
    *,
    task_ref: str,
    target_epic: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Move a task from its current epic to a different epic.

    target_epic: path like "projects/demo/new_epic" or epic ref.
    """
    from trailmind.scopes import resolve_epic_dir

    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")

    # Determine source epic
    source_epic_path = task_path.parent.parent
    source_epic_rel = source_epic_path.relative_to(repo_root).as_posix()

    # Resolve target epic
    target_epic_path = resolve_epic_dir(repo_root, target_epic)
    target_epic_rel = target_epic_path.relative_to(repo_root).as_posix()

    if source_epic_path == target_epic_path:
        raise TrailmindError("task is already in the target epic")

    # Ensure target tasks directory exists
    target_tasks_dir = target_epic_path / "tasks"
    target_tasks_dir.mkdir(parents=True, exist_ok=True)

    # Build new path (same filename)
    new_path = target_tasks_dir / task_path.name
    if new_path.exists():
        raise TrailmindError(f"a task with the same filename already exists in {target_epic_rel}")

    # Add activity entry
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Moved from {source_epic_rel} to {target_epic_rel}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )

    # Write to new location and delete old
    write_entity(new_path, frontmatter=frontmatter, body=body)
    task_path.unlink()

    return new_path


def clone_task(
    repo_root: Path,
    *,
    task_ref: str,
    actor: str,
    title: str | None = None,
    owner: str | None = None,
    target_epic: str | None = None,
    note: str | None = None,
) -> Path:
    """Clone a task, preserving most fields with a new ID.

    Copies: priority, code_paths, design_doc, deliverables, known_issues,
            depends_on, soft_depends_on
    Resets: status (to "created"), created date (to today)
    Overridable: title, owner, target epic
    """
    from trailmind.log import action_activity_entry, append_activity_entry
    from trailmind.scopes import resolve_epic_dir

    source_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    source_fm, _source_body = read_entity_user_facing(source_path, label="task")

    # Determine target epic
    if target_epic:
        target_epic_path = resolve_epic_dir(repo_root, target_epic)
    else:
        target_epic_path = source_path.parent.parent

    source_epic_rel = source_path.parent.parent.relative_to(repo_root).as_posix()
    target_epic_rel = target_epic_path.relative_to(repo_root).as_posix()

    # Resolve actor from roster
    roster = Roster.load(repo_root / "roster.yaml")
    actor_shortname = roster.resolve_shortname(actor)
    actor_uid = None
    for dev in roster.developers:
        if dev.shortname == actor_shortname:
            actor_uid = dev.uid
            break

    # Resolve owner
    owner_ref = owner or actor
    owner_shortname = roster.resolve_shortname(owner_ref)

    # New title or use source
    new_title = title or str(source_fm.get("title") or source_path.stem)

    # Ensure target tasks directory exists
    target_tasks_dir = target_epic_path / "tasks"
    _ensure_tasks_directory(target_tasks_dir)

    # Generate new ID
    new_task_id = next_entity_id(target_tasks_dir, entity="T", uid=actor_uid)
    new_task_path = target_tasks_dir / f"{new_task_id}-{slugify(new_title)}.md"

    if new_task_path.exists():
        raise TrailmindError(f"a task with the same filename already exists in {target_epic_rel}")

    # Build new frontmatter, preserving useful fields
    source_id = str(source_fm.get("id") or source_path.stem)
    new_fm = {
        "id": new_task_id,
        "title": new_title,
        "filer": actor_shortname,
        "owner": owner_shortname,
        "status": "created",
        "priority": str(source_fm.get("priority") or DEFAULT_PRIORITY),
        "created": date.today().isoformat(),
        "start": None,
        "due": None,
        "branches": {},
        "verify": {},
        "code_paths": list(source_fm.get("code_paths") or []),
        "design_doc": source_fm.get("design_doc"),
        "depends_on": list(source_fm.get("depends_on") or []),
        "soft_depends_on": list(source_fm.get("soft_depends_on") or []),
        "known_issues": list(source_fm.get("known_issues") or []),
        "deliverables": list(source_fm.get("deliverables") or []),
        "completed_deliverables": [],
    }

    # Build body with clone note
    today = date.today().isoformat()
    clone_note = f"Cloned from {source_id} ({source_epic_rel})"
    if note:
        clone_note += f". {note}"

    new_body = (
        f"# {new_title}\n\n"
        "## Scope\n\n"
        "TBD\n\n"
        "## Acceptance\n\n"
        "- TBD\n\n"
        "## Activity Log\n\n"
        f"- {today}: Created task by {actor_shortname}.\n"
        f"- {today}: {clone_note} by {actor_shortname}.\n"
    )

    write_entity(new_task_path, frontmatter=new_fm, body=new_body)
    return new_task_path


def comment_task(
    repo_root: Path,
    *,
    task_ref: str,
    author: str,
    text: str,
) -> Path:
    """Add a comment/note to a task's body with date and author stamp."""
    from datetime import datetime

    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    _frontmatter, body = read_entity_user_facing(task_path, label="task")

    # Resolve author shortname
    roster = Roster.load(repo_root / "roster.yaml")
    author_shortname = roster.resolve_shortname(author)

    today = date.today().isoformat()
    timestamp = datetime.now().strftime("%H:%M")

    # Build comment block
    comment = f"> **{author_shortname}** · {today} {timestamp}\n>\n> {text}\n"

    # Insert comment before Activity Log section, or at the end
    if "## Activity Log" in body:
        body = body.replace("## Activity Log\n", f"## Comments\n\n{comment}\n## Activity Log\n", 1)
    elif "## Comments" in body:
        body = body.replace("## Comments\n", f"## Comments\n\n{comment}\n", 1)
    else:
        body = body.rstrip() + f"\n\n## Comments\n\n{comment}\n"

    # Also add an activity entry
    from trailmind.log import action_activity_entry, append_activity_entry
    body = append_activity_entry(
        body,
        action_activity_entry(
            action="Comment added",
            actor_label="author",
            actor=author_shortname,
        ),
    )

    write_entity(task_path, frontmatter=_frontmatter, body=body)
    return task_path
