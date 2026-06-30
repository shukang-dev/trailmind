from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from trailmind.errors import TrailmindError
from trailmind.inbox import InboxItem, open_inbox_items_under
from trailmind.log import read_entity_user_facing
from trailmind.scopes import iter_epic_dirs, resolve_project_dir
from trailmind.task_rules import (
    TaskReferenceStatus,
    dependency_blockers,
    last_activity_date,
    missing_deliverables,
    soft_dependency_warnings,
    task_identity,
)
from trailmind.task_status import normalize_task_status


@dataclass(frozen=True)
class SweepTask:
    task_id: str
    title: str
    status: str
    path: Path
    blockers: list[TaskReferenceStatus] = field(default_factory=list)
    soft_warnings: list[TaskReferenceStatus] = field(default_factory=list)
    missing_deliverables: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SweepReport:
    repo_root: Path
    ready: list[SweepTask]
    blocked: list[SweepTask]
    stale: list[SweepTask]
    missing_deliverables: list[SweepTask]
    open_inbox: list[InboxItem]


def build_sweep_report(
    repo_root: Path,
    *,
    project: str | None,
    epic: str | None,
    stale_days: int,
) -> SweepReport:
    epic_dirs = iter_epic_dirs(repo_root, project=project, epic=epic)
    today = date.today()
    ready: list[SweepTask] = []
    blocked: list[SweepTask] = []
    stale: list[SweepTask] = []
    missing: list[SweepTask] = []
    open_inbox: list[InboxItem] = []

    if project:
        open_inbox.extend(open_inbox_items_under(resolve_project_dir(repo_root, project)))
    elif epic is None:
        projects_path = repo_root / "projects"
        if projects_path.exists() and projects_path.is_dir():
            for project_path in sorted(path for path in projects_path.iterdir() if (path / "PROJECT.md").is_file()):
                open_inbox.extend(open_inbox_items_under(project_path))
    for epic_dir in epic_dirs:
        open_inbox.extend(open_inbox_items_under(epic_dir))
        tasks_dir = epic_dir / "tasks"
        if not tasks_dir.exists():
            continue
        if not tasks_dir.is_dir():
            raise TrailmindError(f"tasks path {tasks_dir} is not a directory")
        for task_path in sorted(tasks_dir.glob("T-*.md")):
            frontmatter, body = read_entity_user_facing(task_path, label="task")
            task_id, title = task_identity(frontmatter, task_path)
            status = normalize_task_status(frontmatter.get("status", "created"))
            if status in {"done", "wontfix"}:
                continue
            blockers = dependency_blockers(repo_root, frontmatter)
            soft_warnings = soft_dependency_warnings(repo_root, frontmatter)
            missing_items = missing_deliverables(frontmatter)
            task = SweepTask(
                task_id=task_id,
                title=title,
                status=status,
                path=task_path,
                blockers=blockers,
                soft_warnings=soft_warnings,
                missing_deliverables=missing_items,
            )
            if status == "blocked" or blockers:
                blocked.append(task)
            elif status in {"created", "ready"}:
                ready.append(task)
            if missing_items:
                missing.append(task)
            last_seen = last_activity_date(frontmatter, body)
            if last_seen is not None and (today - last_seen).days >= stale_days:
                stale.append(task)
    return SweepReport(
        repo_root=repo_root,
        ready=ready,
        blocked=blocked,
        stale=stale,
        missing_deliverables=missing,
        open_inbox=open_inbox,
    )


def format_sweep_report(report: SweepReport) -> str:
    lines = ["Project Automation Sweep"]
    _append_task_section(lines, "Ready", report.ready, repo_root=report.repo_root)
    _append_task_section(lines, "Blocked", report.blocked, repo_root=report.repo_root)
    _append_task_section(lines, "Stale", report.stale, repo_root=report.repo_root)
    _append_missing_deliverables(lines, report.missing_deliverables, repo_root=report.repo_root)
    _append_inbox(lines, report.open_inbox, repo_root=report.repo_root)
    return "\n".join(lines) + "\n"


def _append_task_section(lines: list[str], title: str, tasks: list[SweepTask], *, repo_root: Path) -> None:
    lines.append("")
    lines.append(title)
    if not tasks:
        lines.append("- none")
        return
    for task in tasks:
        suffix = ""
        if task.blockers:
            refs = ", ".join(item.task_id for item in task.blockers)
            suffix = f" - unsatisfied: {refs}"
        elif task.soft_warnings:
            refs = ", ".join(item.task_id for item in task.soft_warnings)
            suffix = f" - soft: {refs}"
        path = _relative_to_root(repo_root, task.path)
        lines.append(f"- {task.task_id} {task.title} [{task.status}] ({path}){suffix}")


def _append_missing_deliverables(lines: list[str], tasks: list[SweepTask], *, repo_root: Path) -> None:
    lines.append("")
    lines.append("Missing deliverables")
    if not tasks:
        lines.append("- none")
        return
    for task in tasks:
        missing = ", ".join(task.missing_deliverables)
        path = _relative_to_root(repo_root, task.path)
        lines.append(f"- {task.task_id} {task.title} ({path}): {missing}")


def _append_inbox(lines: list[str], items: list[InboxItem], *, repo_root: Path) -> None:
    lines.append("")
    lines.append("Open inbox")
    if not items:
        lines.append("- none")
        return
    for item in items:
        path = _relative_to_root(repo_root, item.path)
        lines.append(f"- {item.item_id} {item.title} ({path})")


def _relative_to_root(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
