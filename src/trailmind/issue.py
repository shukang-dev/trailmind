from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.resolver import resolve_entity
from trailmind.roster import Roster


ISSUE_CLOSE_STATUSES = ("done", "wontfix")
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")


def validate_issue_severity(severity: str) -> str:
    normalized = severity.strip().lower()
    if normalized not in ISSUE_SEVERITIES:
        expected = ", ".join(ISSUE_SEVERITIES)
        raise TrailmindError(f"invalid issue severity {severity!r}; expected one of: {expected}")
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


def _relative_path(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _ensure_issues_directory(issues_path: Path) -> None:
    if issues_path.exists() and not issues_path.is_dir():
        raise TrailmindError(f"issues path {issues_path} is not a directory")
    issues_path.mkdir(parents=True, exist_ok=True)


def _initial_body(title: str, description: str, filer: str) -> str:
    return (
        f"# {title}\n\n"
        "## Description\n\n"
        f"{description}\n\n"
        "## Resolution\n\n"
        "TBD\n\n"
        "## Activity Log\n\n"
        f"{action_activity_entry(action='Filed', actor_label='filer', actor=filer)}\n"
    )


def _list_field(frontmatter: dict[str, object], key: str, *, label: str) -> list[object]:
    value = frontmatter.get(key)
    if value is None:
        value = []
        frontmatter[key] = value
    if not isinstance(value, list):
        raise TrailmindError(f"{label} field {key} must be a list")
    return value


def _append_unique(values: list[object], item: str) -> None:
    if item not in values:
        values.append(item)


def _frontmatter_id(frontmatter: dict[str, object], path: Path, *, label: str) -> str:
    raw = frontmatter.get("id")
    if not isinstance(raw, str) or not raw.strip():
        raise TrailmindError(f"{label} file {path} is missing an id")
    return raw.strip()


def _validate_close_status(status: str) -> str:
    if status not in ISSUE_CLOSE_STATUSES:
        expected = ", ".join(ISSUE_CLOSE_STATUSES)
        raise TrailmindError(f"invalid issue close status {status!r}; expected one of: {expected}")
    return status


def list_issues(
    repo_root: Path,
    *,
    epic_ref: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    owner: str | None = None,
    sort_by: str = "created",
) -> list[dict[str, str]]:
    """List issues in an epic or across the repo, with optional filtering and sorting.

    sort_by: "created" (default), "severity", "status", "title"
    """
    from trailmind.scopes import resolve_epic_dir

    if epic_ref:
        epic_path = resolve_epic_dir(repo_root, epic_ref)
        issue_paths = sorted(epic_path.glob("issues/I-*.md"))
    else:
        projects_path = repo_root / "projects"
        if not projects_path.exists() or not projects_path.is_dir():
            return []
        issue_paths = sorted(projects_path.glob("*/*/issues/I-*.md"))

    issues = []
    for path in issue_paths:
        if not path.is_file():
            continue
        try:
            frontmatter, _body = read_entity_user_facing(path, label="issue")
        except TrailmindError:
            continue

        issue_status = str(frontmatter.get("status") or "open")
        issue_severity = str(frontmatter.get("severity") or "")
        issue_owner = str(frontmatter.get("owner") or "")

        if status and issue_status != status:
            continue
        if severity and issue_severity != severity:
            continue
        if owner and issue_owner != owner:
            continue

        issues.append({
            "id": str(frontmatter.get("id") or path.stem),
            "title": str(frontmatter.get("title") or path.stem),
            "status": issue_status,
            "severity": issue_severity,
            "owner": issue_owner,
            "filer": str(frontmatter.get("filer") or ""),
            "created": str(frontmatter.get("created") or ""),
            "path": path.relative_to(repo_root).as_posix(),
        })

    # Sort
    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "": 4}
    STATUS_ORDER = {"open": 0, "in_progress": 1, "done": 2, "wontfix": 3}

    def sort_key(i: dict[str, str]) -> tuple:
        if sort_by == "severity":
            return (SEVERITY_ORDER.get(i["severity"], 4), STATUS_ORDER.get(i["status"], 9), i.get("created", ""))
        elif sort_by == "status":
            return (STATUS_ORDER.get(i["status"], 9), SEVERITY_ORDER.get(i["severity"], 4))
        elif sort_by == "title":
            return (i.get("title", "").lower(),)
        else:  # created
            return (i.get("created", "") or "9999-99-99", SEVERITY_ORDER.get(i["severity"], 4))

    issues.sort(key=sort_key)
    return issues


def add_issue(
    repo_root: Path,
    *,
    epic: str,
    filer: str,
    title: str,
    description: str,
    severity: str,
) -> Path:
    epic_path = _resolve_epic(repo_root, epic)
    roster = Roster.load(repo_root / "roster.yaml")
    filer_shortname = roster.require_shortname(filer)
    filer_uid = roster.require_uid(filer)

    issues_path = epic_path / "issues"
    _ensure_issues_directory(issues_path)
    issue_id = next_entity_id(issues_path, entity="I", uid=filer_uid)
    issue_path = issues_path / f"{issue_id}-{slugify(title)}.md"
    write_entity(
        issue_path,
        frontmatter={
            "id": issue_id,
            "title": title,
            "filer": filer_shortname,
            "owner": filer_shortname,
            "status": "open",
            "severity": severity,
            "created": date.today().isoformat(),
            "linked_tasks": [],
            "carried_into": [],
        },
        body=_initial_body(title, description, filer_shortname),
    )
    return issue_path


def assign_issue(
    repo_root: Path,
    *,
    issue_ref: str,
    owner: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Reassign an issue to a different owner."""
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")

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
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def set_issue_severity(
    repo_root: Path,
    *,
    issue_ref: str,
    severity: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Change an issue's severity."""
    validated = validate_issue_severity(severity)
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")
    old_severity = str(frontmatter.get("severity", "unknown"))

    frontmatter["severity"] = validated
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Severity changed from {old_severity} to {validated}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def edit_issue(
    repo_root: Path,
    *,
    issue_ref: str,
    actor: str,
    title: str | None = None,
    description: str | None = None,
    note: str | None = None,
) -> Path:
    """Edit editable fields on an issue.

    Only provided fields are updated. None means "don't change".
    """
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")

    changes: list[str] = []

    if title is not None and title.strip():
        old_title = str(frontmatter.get("title", ""))
        frontmatter["title"] = title.strip()
        changes.append(f"Title: {old_title} → {title.strip()}")

    if description is not None:
        # Replace the body's "## Description" section or prepend it
        old_body = body
        if "## Description" in old_body:
            import re
            new_body = re.sub(
                r"## Description\n\n.*?(?=\n## |\Z)",
                f"## Description\n\n{description.strip()}",
                old_body,
                count=1,
                flags=re.DOTALL,
            )
            body = new_body
        else:
            body = f"## Description\n\n{description.strip()}\n\n{old_body.lstrip('#')}"
        changes.append("Description updated")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title or --description")

    action = f"Edited issue: {'; '.join(changes)}"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def reopen_issue(
    repo_root: Path,
    *,
    issue_ref: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Reopen a closed issue (done or wontfix → open)."""
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")
    old_status = str(frontmatter.get("status", "open"))

    if old_status not in ISSUE_CLOSE_STATUSES:
        raise TrailmindError(f"cannot reopen issue with status {old_status!r} (must be done or wontfix)")

    frontmatter["status"] = "open"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Reopened (was {old_status})",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def link_issue(repo_root: Path, *, raw_issue: str, raw_task: str) -> list[Path]:
    issue_path = resolve_entity(repo_root, raw=raw_issue, entity="I")
    task_path = resolve_entity(repo_root, raw=raw_task, entity="T")
    issue_frontmatter, issue_body = read_entity_user_facing(issue_path, label="issue")
    task_frontmatter, task_body = read_entity_user_facing(task_path, label="task")

    issue_id = _frontmatter_id(issue_frontmatter, issue_path, label="issue")
    task_id = _frontmatter_id(task_frontmatter, task_path, label="task")
    _append_unique(_list_field(issue_frontmatter, "linked_tasks", label="issue"), task_id)
    _append_unique(_list_field(task_frontmatter, "known_issues", label="task"), issue_id)

    write_entity(issue_path, frontmatter=issue_frontmatter, body=issue_body)
    write_entity(task_path, frontmatter=task_frontmatter, body=task_body)
    return [issue_path, task_path]


def link_issue_to_task(repo_root: Path, *, issue_ref: str, task_ref: str) -> list[Path]:
    return link_issue(repo_root, raw_issue=issue_ref, raw_task=task_ref)


def _coalesce_issue_ref(*, raw_id: str | None, issue_ref: str | None) -> str:
    if raw_id is not None:
        return raw_id
    if issue_ref is not None:
        return issue_ref
    raise TrailmindError("issue reference is required")


def close_issue(
    repo_root: Path,
    *,
    raw_id: str | None = None,
    closer: str,
    status: str,
    note: str,
    issue_ref: str | None = None,
) -> Path:
    status = _validate_close_status(status)
    issue_path = resolve_entity(repo_root, raw=_coalesce_issue_ref(raw_id=raw_id, issue_ref=issue_ref), entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")
    frontmatter["status"] = status
    body = append_activity_entry(
        body,
        action_activity_entry(action=f"Closed as {status}", actor_label="closer", actor=closer, note=note),
    )
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def carry_issue(
    repo_root: Path,
    *,
    raw_issue: str | None = None,
    to_epic: str,
    issue_ref: str | None = None,
) -> list[Path]:
    issue_path = resolve_entity(
        repo_root,
        raw=_coalesce_issue_ref(raw_id=raw_issue, issue_ref=issue_ref),
        entity="I",
    )
    target_epic_dir = _resolve_epic(repo_root, to_epic)
    target_epic_path = target_epic_dir / "EPIC.md"

    issue_frontmatter, issue_body = read_entity_user_facing(issue_path, label="issue")
    target_frontmatter, target_body = read_entity_user_facing(target_epic_path, label="epic")

    target_epic_ref = _relative_path(repo_root, target_epic_dir)
    source_issue_ref = _relative_path(repo_root, issue_path)
    _append_unique(_list_field(issue_frontmatter, "carried_into", label="issue"), target_epic_ref)
    _append_unique(_list_field(target_frontmatter, "carried_issues", label="epic"), source_issue_ref)

    write_entity(issue_path, frontmatter=issue_frontmatter, body=issue_body)
    write_entity(target_epic_path, frontmatter=target_frontmatter, body=target_body)
    return [issue_path, target_epic_path]
