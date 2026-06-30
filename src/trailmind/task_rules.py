from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.errors import TrailmindError
from trailmind.log import read_entity_user_facing
from trailmind.resolver import EntityAmbiguousError, EntityNotFoundError, resolve_entity
from trailmind.task_status import is_terminal_task_status, normalize_task_status


GATED_TASK_STATUSES = {"ready", "in_progress", "done"}
ACTIVITY_DATE_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}):")
SLUG_SUFFIX_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class TaskReferenceStatus:
    ref: str
    path: Path | None
    task_id: str
    title: str
    status: str
    terminal: bool
    missing: bool


@dataclass(frozen=True)
class LinkedIssueStatus:
    issue_id: str
    title: str
    status: str
    path: Path


def string_list_field(frontmatter: dict[str, Any], key: str, *, label: str) -> list[str]:
    value = frontmatter.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise TrailmindError(f"{label} field {key} must be a list")
    return [str(item) for item in value if str(item).strip()]


def _is_path_like_ref(raw: str) -> bool:
    windows_path = PureWindowsPath(raw)
    return (
        raw in {".", ".."}
        or "/" in raw
        or "\\" in raw
        or raw.endswith(".md")
        or PurePosixPath(raw).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    )


def _matches_bare_issue_id(path: Path, raw: str) -> bool:
    stem = path.stem
    if stem == raw:
        return True
    prefix = f"{raw}-"
    if not stem.startswith(prefix):
        return False
    return bool(SLUG_SUFFIX_RE.fullmatch(stem[len(prefix) :]))


def _relative_display(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_linked_issue(repo_root: Path, task_path: Path, ref: str) -> Path:
    if _is_path_like_ref(ref):
        return resolve_entity(repo_root, raw=ref, entity="I")

    local_issues_path = task_path.parent.parent / "issues"
    local_matches = sorted(
        (
            path
            for path in local_issues_path.glob("I-*.md")
            if path.is_file() and _matches_bare_issue_id(path, ref)
        ),
        key=lambda path: _relative_display(repo_root, path),
    )
    if len(local_matches) == 1:
        return local_matches[0]
    if len(local_matches) > 1:
        candidates = ", ".join(_relative_display(repo_root, path) for path in local_matches)
        raise EntityAmbiguousError(f"I entity {ref!r} is ambiguous; candidates: {candidates}")
    return resolve_entity(repo_root, raw=ref, entity="I")


def linked_open_issues_for_task(repo_root: Path, task_path: Path) -> list[LinkedIssueStatus]:
    frontmatter, _body = read_entity_user_facing(task_path, label="task")
    refs = string_list_field(frontmatter, "known_issues", label="task")
    open_issues: list[LinkedIssueStatus] = []
    for ref in refs:
        issue_ref = ref.strip()
        try:
            issue_path = _resolve_linked_issue(repo_root, task_path, issue_ref)
        except EntityNotFoundError:
            continue
        issue_frontmatter, _issue_body = read_entity_user_facing(issue_path, label="issue")
        status = str(issue_frontmatter.get("status", "open")).strip()
        if status != "open":
            continue
        issue_id = str(issue_frontmatter.get("id") or issue_path.stem).strip()
        title = str(issue_frontmatter.get("title") or issue_path.stem).strip()
        open_issues.append(LinkedIssueStatus(issue_id=issue_id, title=title, status=status, path=issue_path))
    return open_issues


def normalize_deliverable_item(value: str) -> str:
    return " ".join(value.split())


def task_identity(frontmatter: dict[str, Any], path: Path) -> tuple[str, str]:
    task_id = str(frontmatter.get("id") or path.stem).strip()
    title = str(frontmatter.get("title") or path.stem).strip()
    return task_id, title


def iter_task_files(repo_root: Path) -> list[Path]:
    projects_path = repo_root / "projects"
    if not projects_path.exists():
        return []
    return sorted(path for path in projects_path.glob("*/*/tasks/T-*.md") if path.is_file())


def _unresolved_task_reference_status(ref: str, *, status: str, title: str) -> TaskReferenceStatus:
    return TaskReferenceStatus(
        ref=ref,
        path=None,
        task_id=ref,
        title=title,
        status=status,
        terminal=False,
        missing=True,
    )


def task_reference_status(repo_root: Path, ref: str, *, soft: bool = False) -> TaskReferenceStatus:
    try:
        task_path = resolve_entity(repo_root, raw=ref, entity="T")
    except EntityNotFoundError:
        return _unresolved_task_reference_status(ref, status="missing", title="missing task")
    except EntityAmbiguousError as exc:
        if not soft:
            raise
        return _unresolved_task_reference_status(ref, status="unresolved", title=str(exc))
    try:
        frontmatter, _body = read_entity_user_facing(task_path, label="task")
        task_id, title = task_identity(frontmatter, task_path)
        status = normalize_task_status(frontmatter.get("status", "created"))
    except TrailmindError as exc:
        if not soft:
            raise
        return _unresolved_task_reference_status(ref, status="unresolved", title=str(exc))
    return TaskReferenceStatus(
        ref=ref,
        path=task_path,
        task_id=task_id,
        title=title,
        status=status,
        terminal=is_terminal_task_status(status),
        missing=False,
    )


def dependency_blockers(repo_root: Path, frontmatter: dict[str, Any]) -> list[TaskReferenceStatus]:
    refs = string_list_field(frontmatter, "depends_on", label="task")
    return [status for status in (task_reference_status(repo_root, ref) for ref in refs) if not status.terminal]


def soft_dependency_warnings(repo_root: Path, frontmatter: dict[str, Any]) -> list[TaskReferenceStatus]:
    refs = string_list_field(frontmatter, "soft_depends_on", label="task")
    statuses = (task_reference_status(repo_root, ref, soft=True) for ref in refs)
    return [status for status in statuses if not status.terminal]


def assert_dependency_gate(repo_root: Path, frontmatter: dict[str, Any], *, target_status: str) -> None:
    if target_status not in GATED_TASK_STATUSES:
        return
    blockers = dependency_blockers(repo_root, frontmatter)
    if blockers:
        details = ", ".join(f"{item.task_id} ({item.status})" for item in blockers)
        raise TrailmindError(f"unsatisfied hard dependencies: {details}")


def missing_deliverables(frontmatter: dict[str, Any]) -> list[str]:
    deliverables = [
        item
        for item in (
            normalize_deliverable_item(item) for item in string_list_field(frontmatter, "deliverables", label="task")
        )
        if item
    ]
    completed = {
        item
        for item in (
            normalize_deliverable_item(item)
            for item in string_list_field(frontmatter, "completed_deliverables", label="task")
        )
        if item
    }
    return [item for item in deliverables if item not in completed]


def assert_deliverables_gate(frontmatter: dict[str, Any], *, target_status: str) -> None:
    if target_status != "done":
        return
    missing = missing_deliverables(frontmatter)
    if missing:
        details = ", ".join(missing)
        raise TrailmindError(f"missing completed deliverables: {details}")


def format_soft_dependency_warning(warnings: list[TaskReferenceStatus]) -> str | None:
    if not warnings:
        return None
    details = ", ".join(f"{item.task_id} ({item.status})" for item in warnings)
    return f"soft dependencies are not terminal: {details}"


def last_activity_date(frontmatter: dict[str, Any], body: str) -> date | None:
    dates: list[date] = []
    created = frontmatter.get("created")
    if isinstance(created, str):
        try:
            dates.append(date.fromisoformat(created))
        except ValueError:
            pass
    for line in body.splitlines():
        match = ACTIVITY_DATE_RE.match(line)
        if not match:
            continue
        try:
            dates.append(date.fromisoformat(match.group(1)))
        except ValueError:
            pass
    return max(dates) if dates else None
