from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trailmind.log import read_entity_user_facing


def build_stats(
    repo_root: Path,
    *,
    project: str | None = None,
    epic: str | None = None,
) -> dict[str, Any]:
    """Build repository statistics.

    If project is specified, only count entities in that project.
    If epic is specified (as a full path like projects/demo/mvp), only count entities in that epic.
    """
    projects_path = repo_root / "projects"
    if not projects_path.exists():
        return {
            "projects": 0,
            "epics": 0,
            "tasks": {"total": 0, "by_status": {}, "by_priority": {}, "by_owner": {}},
            "issues": {"total": 0, "by_status": {}, "by_severity": {}},
            "milestones": 0,
            "inbox": {"total": 0, "open": 0},
            "specs": {"total": 0, "by_status": {}},
            "plans": {"total": 0, "by_status": {}},
            "overdue_tasks": 0,
        }

    project_count = 0
    epic_count = 0
    task_status_counter: Counter[str] = Counter()
    task_priority_counter: Counter[str] = Counter()
    task_owner_counter: Counter[str] = Counter()
    issue_status_counter: Counter[str] = Counter()
    issue_severity_counter: Counter[str] = Counter()
    milestone_count = 0
    inbox_total = 0
    inbox_open = 0
    spec_status_counter: Counter[str] = Counter()
    plan_status_counter: Counter[str] = Counter()
    overdue_tasks = 0
    due_within_7 = 0
    due_within_30 = 0
    active_tasks = 0
    today = date.today().isoformat()
    within_7 = (date.today() + timedelta(days=7)).isoformat()
    within_30 = (date.today() + timedelta(days=30)).isoformat()

    for project_dir in sorted(projects_path.iterdir()):
        if not project_dir.is_dir():
            continue
        project_md = project_dir / "PROJECT.md"
        if not project_md.exists():
            continue
        # Apply project filter
        if project and project_dir.name != project:
            continue
        project_count += 1

        for epic_dir in sorted(project_dir.iterdir()):
            if not epic_dir.is_dir():
                continue
            epic_md = epic_dir / "EPIC.md"
            if not epic_md.exists():
                continue
            # Apply epic filter (supports "projects/demo/mvp" or "mvp")
            if epic:
                epic_rel = f"projects/{project_dir.name}/{epic_dir.name}"
                if epic != epic_rel and epic != epic_dir.name:
                    continue
            epic_count += 1

            # Tasks
            tasks_dir = epic_dir / "tasks"
            if tasks_dir.exists():
                for task_file in sorted(tasks_dir.glob("T-*.md")):
                    if not task_file.is_file():
                        continue
                    try:
                        fm, _body = read_entity_user_facing(task_file, label="task")
                    except Exception:
                        continue
                    status = str(fm.get("status", "created"))
                    priority = str(fm.get("priority", ""))
                    owner = str(fm.get("owner", ""))
                    due = fm.get("due")
                    task_status_counter[status] += 1
                    if priority:
                        task_priority_counter[priority] += 1
                    if owner:
                        task_owner_counter[owner] += 1
                    if due and due < today and status not in ("done", "wontfix"):
                        overdue_tasks += 1
                    if status not in ("done", "wontfix"):
                        active_tasks += 1
                        if due and today <= due <= within_7:
                            due_within_7 += 1
                        if due and today <= due <= within_30:
                            due_within_30 += 1

            # Issues
            issues_dir = epic_dir / "issues"
            if issues_dir.exists():
                for issue_file in sorted(issues_dir.glob("I-*.md")):
                    if not issue_file.is_file():
                        continue
                    try:
                        fm, _body = read_entity_user_facing(issue_file, label="issue")
                    except Exception:
                        continue
                    status = str(fm.get("status", "open"))
                    severity = str(fm.get("severity", ""))
                    issue_status_counter[status] += 1
                    if severity:
                        issue_severity_counter[severity] += 1

            # Milestones
            ms_dir = epic_dir / "milestones"
            if ms_dir.exists():
                for ms_file in sorted(ms_dir.glob("M-*.md")):
                    if ms_file.is_file():
                        milestone_count += 1

            # Inbox
            inbox_dir = epic_dir / "inbox"
            if inbox_dir.exists():
                for inbox_file in sorted(inbox_dir.glob("IN-*.md")):
                    if not inbox_file.is_file():
                        continue
                    try:
                        fm, _body = read_entity_user_facing(inbox_file, label="inbox")
                    except Exception:
                        continue
                    inbox_total += 1
                    status = str(fm.get("status", "open"))
                    if status == "open":
                        inbox_open += 1

            # Specs
            specs_dir = epic_dir / "docs" / "specs"
            if specs_dir.exists():
                for spec_file in sorted(specs_dir.glob("*.md")):
                    if not spec_file.is_file():
                        continue
                    try:
                        fm, _body = read_entity_user_facing(spec_file, label="spec")
                        spec_status = str(fm.get("status", "unknown"))
                        spec_status_counter[spec_status] += 1
                    except Exception:
                        continue

            # Plans
            plans_dir = epic_dir / "docs" / "plans"
            if plans_dir.exists():
                for plan_file in sorted(plans_dir.glob("*.md")):
                    if not plan_file.is_file():
                        continue
                    try:
                        fm, _body = read_entity_user_facing(plan_file, label="plan")
                        plan_status = str(fm.get("status", "unknown"))
                        plan_status_counter[plan_status] += 1
                    except Exception:
                        continue

    total_tasks = sum(task_status_counter.values())
    total_issues = sum(issue_status_counter.values())
    total_specs = sum(spec_status_counter.values())
    total_plans = sum(plan_status_counter.values())

    return {
        "projects": project_count,
        "epics": epic_count,
        "tasks": {
            "total": total_tasks,
            "by_status": dict(task_status_counter),
            "by_priority": dict(task_priority_counter),
            "by_owner": dict(task_owner_counter),
        },
        "issues": {
            "total": total_issues,
            "by_status": dict(issue_status_counter),
            "by_severity": dict(issue_severity_counter),
        },
        "milestones": milestone_count,
        "inbox": {
            "total": inbox_total,
            "open": inbox_open,
        },
        "specs": {
            "total": total_specs,
            "by_status": dict(spec_status_counter),
        },
        "plans": {
            "total": total_plans,
            "by_status": dict(plan_status_counter),
        },
        "overdue_tasks": overdue_tasks,
        "due_within_7_days": due_within_7,
        "due_within_30_days": due_within_30,
        "active_tasks": active_tasks,
    }


def format_stats(stats: dict[str, Any]) -> str:
    """Format stats as a readable text report."""
    lines = []
    lines.append("=== Trailmind Stats ===")
    lines.append("")
    lines.append(f"  Projects:   {stats['projects']}")
    lines.append(f"  Epics:      {stats['epics']}")
    lines.append(f"  Milestones: {stats['milestones']}")
    lines.append("")

    tasks = stats["tasks"]
    lines.append(f"  Tasks:      {tasks['total']}")
    if tasks["by_status"]:
        lines.append("    By status:")
        for status, count in sorted(tasks["by_status"].items()):
            lines.append(f"      {status:14s} {count}")
    if tasks["by_priority"]:
        lines.append("    By priority:")
        for priority, count in sorted(tasks["by_priority"].items()):
            lines.append(f"      {priority:14s} {count}")
    if tasks["by_owner"]:
        lines.append("    By owner:")
        for owner, count in sorted(tasks["by_owner"].items(), key=lambda x: -x[1]):
            lines.append(f"      {owner:14s} {count}")
    if stats.get("overdue_tasks"):
        lines.append(f"    Overdue:    {stats['overdue_tasks']}")
    if stats.get("due_within_7_days"):
        lines.append(f"    Due in 7d:  {stats['due_within_7_days']}")
    if stats.get("due_within_30_days"):
        lines.append(f"    Due in 30d: {stats['due_within_30_days']}")
    if stats.get("active_tasks") or tasks["total"] > 0:
        done = tasks["by_status"].get("done", 0)
        total = tasks["total"]
        if total > 0:
            pct = round(done / total * 100)
            lines.append(f"    Progress:   {done}/{total} done ({pct}%)")
    lines.append("")

    issues = stats["issues"]
    lines.append(f"  Issues:     {issues['total']}")
    if issues["by_status"]:
        lines.append("    By status:")
        for status, count in sorted(issues["by_status"].items()):
            lines.append(f"      {status:14s} {count}")
    if issues["by_severity"]:
        lines.append("    By severity:")
        for severity, count in sorted(issues["by_severity"].items()):
            lines.append(f"      {severity:14s} {count}")
    lines.append("")

    inbox = stats["inbox"]
    lines.append(f"  Inbox:      {inbox['total']} ({inbox['open']} open)")

    specs = stats.get("specs", {"total": 0, "by_status": {}})
    if specs["total"]:
        lines.append("")
        lines.append(f"  Specs:      {specs['total']}")
        if specs["by_status"]:
            for status, count in sorted(specs["by_status"].items()):
                lines.append(f"      {status:30s} {count}")

    plans = stats.get("plans", {"total": 0, "by_status": {}})
    if plans["total"]:
        lines.append(f"  Plans:      {plans['total']}")
        if plans["by_status"]:
            for status, count in sorted(plans["by_status"].items()):
                lines.append(f"      {status:30s} {count}")

    return "\n".join(lines) + "\n"
