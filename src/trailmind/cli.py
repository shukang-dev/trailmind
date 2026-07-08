from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from trailmind import __version__
from trailmind.dashboard import (
    render_epic_dashboard,
    render_epic_dashboard_at,
    render_overview,
    render_project_dashboard,
    render_project_dashboard_at,
)
from trailmind.doctor import format_doctor_report, run_doctor
from trailmind.epic import EPIC_STATES, edit_epic, init_epic, set_epic_status, validate_epic_state
from trailmind.errors import TrailmindError
from trailmind.export import export_repo, format_export
from trailmind.importer import import_repo, load_export_file
from trailmind.inbox import add_inbox_item, edit_inbox_item, list_inbox_items, resolve_inbox_item
from trailmind.issue import (
    ISSUE_SEVERITIES,
    add_issue,
    assign_issue,
    carry_issue,
    close_issue,
    clone_issue,
    comment_issue,
    edit_issue,
    link_issue,
    list_issues,
    move_issue,
    rename_issue,
    reopen_issue,
    set_issue_severity,
)
from trailmind.log import log_activity
from trailmind.milestone import MILESTONE_STATUSES, add_milestone, edit_milestone, list_milestones, set_milestone_status
from trailmind.paths import find_repo_root
from trailmind.pickup import (
    build_issue_pickup,
    build_task_pickup,
    format_pickup_markdown,
    log_issue_pickup,
    log_task_pickup,
    pickup_pack_to_dict,
)
from trailmind.plan_breakdown import (
    breakdown_report_to_dict,
    build_breakdown_report,
    format_breakdown_markdown,
)
from trailmind.plan_artifact import (
    PLAN_STATUSES,
    SPEC_STATUSES,
    _resolve_any_doc,
    build_planning_status,
    create_plan,
    create_spec,
    format_planning_status_markdown,
    link_plan_spec,
    list_plans,
    list_specs,
    parse_plan_info,
    parse_spec_info,
    planning_status_to_dict,
    set_plan_status,
    set_spec_status,
)
from trailmind.project import PROJECT_STATES, edit_project, init_project, set_project_status, validate_project_state
from trailmind.roster import Roster
from trailmind.security_scan import scan_paths
from trailmind.activity import collect_activity
from trailmind.search import search_entities
from trailmind.tree import build_tree, format_tree
from trailmind.serve import serve_repo
from trailmind.show import format_entity_show, show_entity
from trailmind.stats import build_stats, format_stats
from trailmind.sweep import build_sweep_report, format_sweep_report, sweep_report_to_dict
from trailmind.task import (
    DEFAULT_PRIORITY,
    TASK_PRIORITIES,
    add_task,
    add_task_deliverable,
    add_task_dependency,
    assign_task,
    close_task,
    clone_task,
    comment_task,
    complete_task,
    complete_task_deliverable,
    edit_task,
    list_tasks,
    move_task,
    next_tasks,
    normalize_task_statuses,
    remove_task_dependency,
    rename_task,
    set_task_due,
    set_task_priority,
    set_task_status,
    split_csv,
    start_task,
    update_task_status,
)
from trailmind.task_rules import linked_open_issues_for_task
from trailmind.task_status import TASK_STATUSES


@click.group()
@click.version_option(__version__, prog_name="trailmind")
def cli() -> None:
    """Trailmind: Markdown-backed project tracking and AI agent handoff."""


@cli.command("init")
@click.option("--with-ci/--no-ci", default=True, help="Create GitHub Actions CI workflow.")
@click.option("--with-templates/--no-templates", default=True, help="Create PR and issue templates.")
@click.pass_context
def init_command(ctx: click.Context, with_ci: bool, with_templates: bool) -> None:
    """Initialize a Trailmind repository with recommended files."""
    root = find_repo_root(_cwd_from_context(ctx))
    created: list[Path] = []

    # roster.yaml
    roster_path = root / "roster.yaml"
    if not roster_path.exists():
        roster_path.write_text("developers: []\n", encoding="utf-8")
        created.append(roster_path)
        click.echo(f"Created {roster_path.relative_to(root).as_posix()}")
    else:
        click.echo(f"roster.yaml already exists, skipping.")

    # projects/ directory
    projects_dir = root / "projects"
    if not projects_dir.exists():
        projects_dir.mkdir(parents=True, exist_ok=True)
        click.echo("Created projects/")

    if with_ci:
        ci_dir = root / ".github" / "workflows"
        ci_dir.mkdir(parents=True, exist_ok=True)
        ci_path = ci_dir / "ci.yml"
        if not ci_path.exists():
            ci_path.write_text(_CI_WORKFLOW, encoding="utf-8")
            created.append(ci_path)
            click.echo(f"Created {ci_path.relative_to(root).as_posix()}")
        else:
            click.echo(".github/workflows/ci.yml already exists, skipping.")

    if with_templates:
        gh_dir = root / ".github"
        gh_dir.mkdir(parents=True, exist_ok=True)

        pr_path = gh_dir / "PULL_REQUEST_TEMPLATE.md"
        if not pr_path.exists():
            pr_path.write_text(_PR_TEMPLATE, encoding="utf-8")
            created.append(pr_path)
            click.echo(f"Created {pr_path.relative_to(root).as_posix()}")

        issue_dir = gh_dir / "ISSUE_TEMPLATE"
        issue_dir.mkdir(parents=True, exist_ok=True)
        bug_path = issue_dir / "bug_report.md"
        if not bug_path.exists():
            bug_path.write_text(_BUG_REPORT_TEMPLATE, encoding="utf-8")
            created.append(bug_path)
            click.echo(f"Created {bug_path.relative_to(root).as_posix()}")
        feat_path = issue_dir / "feature_request.md"
        if not feat_path.exists():
            feat_path.write_text(_FEATURE_REQUEST_TEMPLATE, encoding="utf-8")
            created.append(feat_path)
            click.echo(f"Created {feat_path.relative_to(root).as_posix()}")

    if not created:
        click.echo("Nothing to create — already initialized.")
    else:
        click.echo(f"\nInitialized Trailmind repo with {len(created)} file(s).")
        click.echo("Next: add a developer to the roster:")
        click.echo("  trailmind roster add --email you@example.com --shortname you --name \"Your Name\"")


_CI_WORKFLOW = """name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"

      - name: Run tests
        run: python -m pytest -v

      - name: Run security scan
        run: PYTHONPATH=src python -m trailmind scan
"""

_PR_TEMPLATE = """## Summary

Brief description of what this PR does.

## Changes

-
-

## Testing

```sh
python -m pytest -v
PYTHONPATH=src python -m trailmind scan
```

- [ ] All tests pass
- [ ] Security scan passes
- [ ] Public docs updated if needed
- [ ] No private data in examples (use `example.com` identities)

## Related Issues

<!-- Link to related issues or specs -->
"""

_BUG_REPORT_TEMPLATE = """---
name: Bug Report
about: Report a bug in Trailmind
title: "[Bug] "
labels: bug
---

## Description

Brief description of the bug.

## Steps to Reproduce

1.
2.
3.

## Expected Behavior

What did you expect to happen?

## Actual Behavior

What actually happened?

## Environment

- OS:
- Python version:
- Trailmind version:

## Logs / Error Messages

```
Paste error output here
```
"""

_FEATURE_REQUEST_TEMPLATE = """---
name: Feature Request
about: Suggest a feature for Trailmind
title: "[Feature] "
labels: enhancement
---

## Description

Brief description of the feature.

## Use Case

Why do you need this? What problem does it solve?

## Proposed Solution

How should this work?

## Alternatives Considered

Any other approaches you considered?
"""


@cli.command("status")
@click.option("--overview", is_flag=True, help="Render the repository overview dashboard.")
@click.option("--project", "project_slug", default=None, help="Render a project dashboard.")
@click.option("--epic", "epic_ref", default=None, help="Render an epic dashboard.")
@click.pass_context
def status_command(ctx: click.Context, overview: bool, project_slug: str | None, epic_ref: str | None) -> None:
    cwd = _cwd_from_context(ctx)
    root = find_repo_root(cwd)
    selected = sum(1 for item in [overview, project_slug, epic_ref] if item)
    if selected > 1:
        raise TrailmindError("status accepts only one scope flag")

    if overview:
        touched = render_overview(root)
    elif project_slug:
        touched = render_project_dashboard(root, project_slug)
    elif epic_ref:
        touched = render_epic_dashboard(root, epic_ref)
    elif (cwd / "EPIC.md").is_file():
        touched = render_epic_dashboard_at(root, cwd)
    elif (cwd / "PROJECT.md").is_file():
        touched = render_project_dashboard_at(root, cwd)
    else:
        touched = render_overview(root)

    _echo_touched(root, [touched])


@cli.command("sweep")
@click.option("--project", "project_slug", default=None)
@click.option("--epic", "epic_ref", default=None)
@click.option("--stale-days", default=7, show_default=True, type=click.IntRange(min=1))
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.pass_context
def sweep_command(ctx: click.Context, project_slug: str | None, epic_ref: str | None, stale_days: int, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    selected = sum(1 for item in [project_slug, epic_ref] if item)
    if selected > 1:
        raise TrailmindError("sweep accepts only one scope flag")
    report = build_sweep_report(root, project=project_slug, epic=epic_ref, stale_days=stale_days)
    if json_output:
        click.echo(json.dumps(sweep_report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        click.echo(format_sweep_report(report), nl=False)


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8888, show_default=True, type=int)
@click.pass_context
def serve_command(ctx: click.Context, host: str, port: int) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    serve_repo(root, host=host, port=port)


@cli.command("completion")
@click.argument("shell", type=click.Choice(("bash", "zsh", "fish"), case_sensitive=False))
def completion_command(shell: str) -> None:
    """Generate shell completion script.

    Usage:
      # Bash
      trailmind completion bash >> ~/.bashrc

      # Zsh
      trailmind completion zsh > ~/.zfunc/_trailmind

      # Fish
      trailmind completion fish > ~/.config/fish/completions/trailmind.fish
    """
    import subprocess
    import sys
    env = {**__import__("os").environ, "_TRAILMIND_COMPLETE": f"{shell}_source"}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "trailmind"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        click.echo(result.stdout, nl=False)
    except Exception as exc:
        raise TrailmindError(f"failed to generate completion: {exc}")


@cli.command("scan")
@click.pass_context
def scan_command(ctx: click.Context) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    findings = scan_paths([root])
    for finding in findings:
        click.echo(f"{_relative_to_root(root, finding.path)}: {finding.message}", err=True)
    if findings:
        count = len(findings)
        noun = "finding" if count == 1 else "findings"
        raise TrailmindError(f"security scan found {count} {noun}")
    click.echo("scan passed")


@cli.command("stats")
@click.option("--project", default=None, help="Show stats for a specific project.")
@click.option("--epic", default=None, help="Show stats for a specific epic (path or slug).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of text report.")
@click.pass_context
def stats_command(ctx: click.Context, project: str | None, epic: str | None, json_output: bool) -> None:
    """Show repository statistics."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = build_stats(root, project=project, epic=epic)
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_stats(data), nl=False)


@cli.command("tree")
@click.option("--project", default=None, help="Show tree for a specific project.")
@click.option("--epic", default=None, help="Show tree for a specific epic (path or slug).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def tree_command(ctx: click.Context, project: str | None, epic: str | None, json_output: bool) -> None:
    """Show project structure as a tree with entity counts."""
    root = find_repo_root(_cwd_from_context(ctx))
    tree = build_tree(root, project=project, epic=epic)
    if json_output:
        click.echo(json.dumps(tree, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_tree(tree))


@cli.command("path")
@click.argument("entity_ref")
@click.option("--type", "entity_type", default="task",
              type=click.Choice(("task", "issue", "milestone", "inbox"), case_sensitive=False),
              help="Entity type (default: task).")
@click.pass_context
def path_command(ctx: click.Context, entity_ref: str, entity_type: str) -> None:
    """Print the file path of an entity."""
    from trailmind.resolver import resolve_entity
    root = find_repo_root(_cwd_from_context(ctx))
    prefix_map = {"task": "T", "issue": "I", "milestone": "M", "inbox": "IN"}
    prefix = prefix_map.get(entity_type, "T")
    try:
        path = resolve_entity(root, raw=entity_ref, entity=prefix)
        click.echo(str(path))
    except TrailmindError as exc:
        raise exc


@cli.command("open")
@click.argument("entity_ref")
@click.option("--type", "entity_type", default="task",
              type=click.Choice(("task", "issue", "milestone", "inbox"), case_sensitive=False),
              help="Entity type (default: task).")
@click.pass_context
def open_command(ctx: click.Context, entity_ref: str, entity_type: str) -> None:
    """Open an entity file in $EDITOR."""
    import os
    import subprocess
    from trailmind.resolver import resolve_entity
    root = find_repo_root(_cwd_from_context(ctx))
    prefix_map = {"task": "T", "issue": "I", "milestone": "M", "inbox": "IN"}
    prefix = prefix_map.get(entity_type, "T")
    path = resolve_entity(root, raw=entity_ref, entity=prefix)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    click.echo(f"Opening {path} with {editor}...")
    try:
        subprocess.run([editor, str(path)], check=False)
    except FileNotFoundError:
        raise TrailmindError(f"editor not found: {editor}; set $EDITOR")


@cli.command("comment")
@click.argument("entity_ref")
@click.argument("text")
@click.option("--type", "entity_type", default="task",
              type=click.Choice(("task", "issue"), case_sensitive=False),
              help="Entity type (default: task).")
@click.option("--author", required=True, help="Author shortname.")
@click.pass_context
def comment_command(ctx: click.Context, entity_ref: str, text: str,
                     entity_type: str, author: str) -> None:
    """Add a comment to a task or issue."""
    root = find_repo_root(_cwd_from_context(ctx))
    if entity_type == "task":
        from trailmind.task import comment_task
        touched = comment_task(root, task_ref=entity_ref, author=author, text=text)
    else:  # issue
        from trailmind.issue import comment_issue
        touched = comment_issue(root, issue_ref=entity_ref, author=author, text=text)
    _echo_touched(root, [touched])


@cli.command("doctor")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of text report.")
@click.pass_context
def doctor_command(ctx: click.Context, json_output: bool) -> None:
    """Diagnose common issues in a Trailmind repo."""
    root = find_repo_root(_cwd_from_context(ctx))
    findings = run_doctor(root)
    if json_output:
        data = [
            {"severity": f.severity, "message": f.message, "path": f.path}
            for f in findings
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        click.echo(format_doctor_report(findings), nl=False)
        errors = sum(1 for f in findings if f.severity == "error")
        if errors:
            raise TrailmindError(f"doctor found {errors} error(s)")


@cli.command("health")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def health_command(ctx: click.Context, json_output: bool) -> None:
    """Quick health check: doctor findings + key stats in one view."""
    from datetime import date
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()

    # Doctor findings
    findings = run_doctor(root)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    # Stats
    all_tasks = list_tasks(root)
    all_issues = list_issues(root)
    all_milestones = list_milestones(root)

    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]
    done_tasks = [t for t in all_tasks if t.get("status") == "done"]
    overdue = [t for t in active_tasks if t.get("due") and t["due"] < today]
    blocked = [t for t in active_tasks if t.get("status") == "blocked"]
    unassigned = [t for t in active_tasks if not t.get("owner")]

    open_issues = [i for i in all_issues if i.get("status") not in ("done", "wontfix")]
    critical_issues = [i for i in open_issues if i.get("severity") == "critical"]

    upcoming_milestones = sorted(
        [m for m in all_milestones if m.get("date") and m["date"] >= today and m.get("status") != "done"],
        key=lambda m: m.get("date", "")
    )[:3]

    # Health score
    score = 100
    score -= len(errors) * 15
    score -= len(warnings) * 5
    score -= len(overdue) * 3
    score -= len(blocked) * 2
    score -= len(unassigned) * 1
    score -= len(critical_issues) * 10
    score = max(0, min(100, score))

    if score >= 80:
        health_emoji = "🟢"
        health_label = "Good"
    elif score >= 60:
        health_emoji = "🟡"
        health_label = "Fair"
    elif score >= 40:
        health_emoji = "🟠"
        health_label = "Needs attention"
    else:
        health_emoji = "🔴"
        health_label = "Critical"

    if json_output:
        data = {
            "score": score,
            "status": health_label.lower(),
            "doctor": {
                "errors": len(errors),
                "warnings": len(warnings),
            },
            "tasks": {
                "total": len(all_tasks),
                "active": len(active_tasks),
                "done": len(done_tasks),
                "overdue": len(overdue),
                "blocked": len(blocked),
                "unassigned": len(unassigned),
            },
            "issues": {
                "total": len(all_issues),
                "open": len(open_issues),
                "critical": len(critical_issues),
            },
            "milestones": {
                "upcoming": len(upcoming_milestones),
            },
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"{health_emoji} Health Score: {score}/100 ({health_label})")
    lines.append("")

    # Doctor
    lines.append(f"🩺 Doctor: {len(errors)} errors, {len(warnings)} warnings")
    if errors:
        for f in errors[:3]:
            lines.append(f"  ❌ {f.message}")
    if warnings:
        for f in warnings[:3]:
            lines.append(f"  ⚠️  {f.message}")
    lines.append("")

    # Tasks
    pct = round(len(done_tasks) / len(all_tasks) * 100) if all_tasks else 0
    lines.append(f"📋 Tasks: {len(done_tasks)}/{len(all_tasks)} done ({pct}%)")
    if overdue:
        lines.append(f"  ⚠️  {len(overdue)} overdue")
    if blocked:
        lines.append(f"  🚧 {len(blocked)} blocked")
    if unassigned:
        lines.append(f"  👤 {len(unassigned)} unassigned")
    lines.append("")

    # Issues
    lines.append(f"🐛 Issues: {len(open_issues)} open")
    if critical_issues:
        lines.append(f"  🔥 {len(critical_issues)} critical")
    lines.append("")

    # Milestones
    if upcoming_milestones:
        lines.append("🏁 Upcoming:")
        for m in upcoming_milestones:
            lines.append(f"  {m['date']}  {m['title']}")
        lines.append("")

    # Recommendations
    recs = []
    if errors:
        recs.append("Fix doctor errors")
    if overdue:
        recs.append("Address overdue tasks")
    if blocked:
        recs.append("Unblock blocked tasks")
    if unassigned:
        recs.append("Assign unassigned tasks")
    if critical_issues:
        recs.append("Triage critical issues")
    if recs:
        lines.append("💡 Recommendations:")
        for r in recs:
            lines.append(f"  - {r}")

    click.echo("\n".join(lines))


@cli.command("summary")
@click.option("--project", default=None, help="Show summary for a specific project.")
@click.option("--epic", default=None, help="Show summary for a specific epic.")
@click.option("--owner", default=None, help="Show summary for a specific owner.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of text report.")
@click.pass_context
def summary_command(ctx: click.Context, project: str | None, epic: str | None,
                     owner: str | None, json_output: bool) -> None:
    """Show a quick daily summary of work status."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))

    # Collect tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    today = date.today().isoformat()
    within_7 = (date.today() + timedelta(days=7)).isoformat()
    within_30 = (date.today() + timedelta(days=30)).isoformat()

    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]
    overdue_tasks = [t for t in active_tasks if t.get("due") and t["due"] < today]
    due_today_tasks = [t for t in active_tasks if t.get("due") == today]
    due_week_tasks = [t for t in active_tasks if t.get("due") and today < t["due"] <= within_7]
    blocked_tasks = [t for t in active_tasks if t.get("status") == "blocked"]
    in_progress_tasks = [t for t in active_tasks if t.get("status") == "in_progress"]
    ready_tasks = [t for t in active_tasks if t.get("status") in ("ready", "created")]
    done_tasks = [t for t in all_tasks if t.get("status") == "done"]

    # Collect issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    open_issues = [i for i in all_issues if i.get("status") not in ("done", "wontfix")]
    critical_issues = [i for i in open_issues if i.get("severity") == "critical"]
    high_issues = [i for i in open_issues if i.get("severity") == "high"]

    # Collect inbox
    from trailmind.inbox import list_inbox_items
    if project or epic:
        inbox_items = list_inbox_items(root, project=project, epic=epic)
    else:
        inbox_items = []
        projects_dir = root / "projects"
        if projects_dir.exists():
            for proj_dir in sorted(projects_dir.iterdir()):
                if not proj_dir.is_dir():
                    continue
                try:
                    inbox_items.extend(list_inbox_items(root, project=proj_dir.name, epic=None))
                except TrailmindError:
                    pass
    open_inbox = [i for i in inbox_items if i.status == "open"]

    # Collect milestones
    milestones = list_milestones(root, epic_ref=epic, project_ref=project)
    active_milestones = [m for m in milestones if m.get("status") != "done"]
    upcoming_milestones = sorted(
        [m for m in active_milestones if m.get("date") and m["date"] >= today],
        key=lambda m: m.get("date", "")
    )[:3]

    # Next tasks
    next_task_list = next_tasks(root, owner=owner, epic=epic, project=project, limit=5)

    if json_output:
        data = {
            "tasks": {
                "total": len(all_tasks),
                "active": len(active_tasks),
                "done": len(done_tasks),
                "in_progress": len(in_progress_tasks),
                "blocked": len(blocked_tasks),
                "ready": len(ready_tasks),
                "overdue": len(overdue_tasks),
                "due_today": len(due_today_tasks),
                "due_this_week": len(due_week_tasks),
            },
            "issues": {
                "total": len(all_issues),
                "open": len(open_issues),
                "critical": len(critical_issues),
                "high": len(high_issues),
            },
            "inbox": {
                "total": len(inbox_items),
                "open": len(open_inbox),
            },
            "milestones": {
                "total": len(milestones),
                "active": len(active_milestones),
                "upcoming": [{"title": m["title"], "date": m["date"]} for m in upcoming_milestones],
            },
            "next_tasks": [
                {"id": t["id"], "title": t["title"], "priority": t.get("priority", ""),
                 "due": t.get("due", ""), "owner": t.get("owner", "")}
                for t in next_task_list
            ],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Text report
    lines = []
    scope = ""
    if epic:
        scope = f" for {epic}"
    elif project:
        scope = f" for {project}"

    lines.append(f"📊 Trailmind Summary{scope}")
    lines.append(f"   {date.today().isoformat()}")
    lines.append("")

    # Tasks section
    lines.append(f"📋 Tasks: {len(active_tasks)} active / {len(all_tasks)} total")
    if done_tasks:
        pct = round(len(done_tasks) / len(all_tasks) * 100) if all_tasks else 0
        lines.append(f"   ✅ {len(done_tasks)} done ({pct}%)")
    if in_progress_tasks:
        lines.append(f"   🔧 {len(in_progress_tasks)} in progress")
    if blocked_tasks:
        lines.append(f"   🚧 {len(blocked_tasks)} blocked")
    if ready_tasks:
        lines.append(f"   ⏳ {len(ready_tasks)} ready to start")
    if overdue_tasks:
        lines.append(f"   ⚠️  {len(overdue_tasks)} overdue")
    if due_today_tasks:
        lines.append(f"   📍 {len(due_today_tasks)} due today")
    if due_week_tasks:
        lines.append(f"   📆 {len(due_week_tasks)} due this week")
    lines.append("")

    # Issues section
    if open_issues:
        lines.append(f"🐛 Issues: {len(open_issues)} open")
        if critical_issues:
            lines.append(f"   🔥 {len(critical_issues)} critical")
        if high_issues:
            lines.append(f"   ⚡ {len(high_issues)} high")
        lines.append("")

    # Inbox section
    if open_inbox:
        lines.append(f"📥 Inbox: {len(open_inbox)} open items")
        lines.append("")

    # Milestones section
    if upcoming_milestones:
        lines.append("🏁 Upcoming milestones:")
        for m in upcoming_milestones:
            lines.append(f"   {m['date']}  {m['title']}")
        lines.append("")

    # Next tasks section
    if next_task_list:
        lines.append("🎯 Next tasks:")
        for i, t in enumerate(next_task_list[:5], 1):
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            due = f"due:{t.get('due', '')}" if t.get('due') else ""
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {i}. {t['id']} {pri} {owner_str} {due}  {t['title']}")
        lines.append("")

    # Quick stats
    lines.append("💡 Quick commands:")
    lines.append("   trailmind task next          — what to work on")
    lines.append("   trailmind task list --overdue — overdue tasks")
    lines.append("   trailmind inbox list         — review inbox")
    lines.append("   trailmind stats              — full statistics")

    click.echo("\n".join(lines))


@cli.command("today")
@click.option("--owner", default=None, help="Show today's view for a specific owner.")
@click.option("--project", default=None, help="Show today's view for a specific project.")
@click.option("--epic", default=None, help="Show today's view for a specific epic.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def today_command(ctx: click.Context, owner: str | None, project: str | None,
                   epic: str | None, json_output: bool) -> None:
    """Quick daily view: due today, overdue, in-progress, and next tasks."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]
    overdue_tasks = [t for t in active_tasks if t.get("due") and t["due"] < today]
    due_today_tasks = [t for t in active_tasks if t.get("due") == today]
    in_progress_tasks = [t for t in active_tasks if t.get("status") == "in_progress"]
    blocked_tasks = [t for t in active_tasks if t.get("status") == "blocked"]
    ready_tasks = [t for t in active_tasks if t.get("status") in ("ready", "created")]
    done_today = [t for t in all_tasks if t.get("status") == "done"]

    # Issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    open_issues = [i for i in all_issues if i.get("status") not in ("done", "wontfix")]

    # Inbox
    from trailmind.inbox import list_inbox_items
    inbox_items = []
    if project or epic:
        try:
            inbox_items = list_inbox_items(root, project=project, epic=epic)
        except TrailmindError:
            pass
    open_inbox = [i for i in inbox_items if i.status == "open"]

    # Next tasks
    next_task_list = next_tasks(root, owner=owner, epic=epic, project=project, limit=5)

    if json_output:
        data = {
            "date": today,
            "tasks": {
                "overdue": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "owner": t.get("owner", "")} for t in overdue_tasks],
                "due_today": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")} for t in due_today_tasks],
                "in_progress": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")} for t in in_progress_tasks],
                "blocked": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")} for t in blocked_tasks],
                "ready": len(ready_tasks),
                "done_today": len(done_today),
            },
            "issues": {
                "open": len(open_issues),
            },
            "inbox": {
                "open": len(open_inbox),
            },
            "next_tasks": [
                {"id": t["id"], "title": t["title"], "priority": t.get("priority", ""), "due": t.get("due", ""), "owner": t.get("owner", "")}
                for t in next_task_list
            ],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"☀️  Today — {today}")
    lines.append("")

    # Due today
    if due_today_tasks:
        lines.append(f"📍 Due today ({len(due_today_tasks)}):")
        for t in due_today_tasks:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {pri} {owner_str}  {t['title']}")
        lines.append("")

    # Overdue
    if overdue_tasks:
        lines.append(f"⚠️  Overdue ({len(overdue_tasks)}):")
        for t in overdue_tasks:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {pri} {owner_str} due:{t.get('due', '')}  {t['title']}")
        lines.append("")

    # In progress
    if in_progress_tasks:
        lines.append(f"🔧 In progress ({len(in_progress_tasks)}):")
        for t in in_progress_tasks:
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {owner_str}  {t['title']}")
        lines.append("")

    # Blocked
    if blocked_tasks:
        lines.append(f"🚧 Blocked ({len(blocked_tasks)}):")
        for t in blocked_tasks:
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {owner_str}  {t['title']}")
        lines.append("")

    # Open issues
    if open_issues:
        lines.append(f"🐛 Open issues: {len(open_issues)}")
        lines.append("")

    # Open inbox
    if open_inbox:
        lines.append(f"📥 Inbox items: {len(open_inbox)}")
        lines.append("")

    # Next tasks
    if next_task_list:
        lines.append("🎯 Pick up next:")
        for i, t in enumerate(next_task_list[:5], 1):
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            due = f"due:{t.get('due', '')}" if t.get('due') else ""
            owner_str = f"@{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {i}. {t['id']} {pri} {owner_str} {due}  {t['title']}")
        lines.append("")

    # Summary line
    lines.append(f"💡 {len(active_tasks)} active tasks · {len(ready_tasks)} ready to start")
    if done_today:
        lines.append(f"   ✅ {len(done_today)} completed")

    # If nothing at all
    if not (due_today_tasks or overdue_tasks or in_progress_tasks or blocked_tasks or
            open_issues or open_inbox or next_task_list):
        lines.append("All caught up! 🎉")

    click.echo("\n".join(lines))


@cli.command("focus")
@click.argument("owner")
@click.option("--project", default=None, help="Focus on a specific project.")
@click.option("--epic", default=None, help="Focus on a specific epic.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def focus_command(ctx: click.Context, owner: str, project: str | None,
                   epic: str | None, json_output: bool) -> None:
    """Focus view: what a specific person should work on today."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()
    within_7 = (date.today() + timedelta(days=7)).isoformat()

    # Get this person's tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]
    overdue = [t for t in active_tasks if t.get("due") and t["due"] < today]
    due_today = [t for t in active_tasks if t.get("due") == today]
    due_week = [t for t in active_tasks if t.get("due") and today < t["due"] <= within_7]
    in_progress = [t for t in active_tasks if t.get("status") == "in_progress"]
    blocked = [t for t in active_tasks if t.get("status") == "blocked"]
    ready = [t for t in active_tasks if t.get("status") in ("ready", "created")]
    done = [t for t in all_tasks if t.get("status") == "done"]

    # Get this person's issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    my_issues = [i for i in all_issues if i.get("owner") == owner and i.get("status") not in ("done", "wontfix")]

    # Get next tasks
    next_task_list = next_tasks(root, owner=owner, epic=epic, project=project, limit=10)

    # Get linked open issues for my tasks
    from trailmind.task_rules import linked_open_issues_for_task
    linked_issues = []
    for t in in_progress + blocked + due_today[:3]:
        try:
            linked = linked_open_issues_for_task(root, t.get("path", ""))
            linked_issues.extend(linked)
        except Exception:
            pass

    if json_output:
        data = {
            "owner": owner,
            "date": today,
            "tasks": {
                "active": len(active_tasks),
                "done": len(done),
                "in_progress": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "epic": t.get("epic", "")} for t in in_progress],
                "blocked": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "epic": t.get("epic", "")} for t in blocked],
                "overdue": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "epic": t.get("epic", "")} for t in overdue],
                "due_today": [{"id": t["id"], "title": t["title"], "epic": t.get("epic", "")} for t in due_today],
                "due_this_week": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "epic": t.get("epic", "")} for t in due_week],
                "ready": len(ready),
            },
            "issues": {
                "assigned": len(my_issues),
                "linked_to_active_tasks": len(linked_issues),
            },
            "next_tasks": [
                {"id": t["id"], "title": t["title"], "priority": t.get("priority", ""),
                 "due": t.get("due", ""), "epic": t.get("epic", "")}
                for t in next_task_list
            ],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🎯 Focus: @{owner}")
    lines.append(f"   {today}")
    lines.append("")

    # In progress — most important
    if in_progress:
        lines.append(f"🔧 In progress ({len(in_progress)}):")
        for t in in_progress:
            due = f" due:{t.get('due', '')}" if t.get('due') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']}{epic}{due}  {t['title']}")
        lines.append("")

    # Blocked
    if blocked:
        lines.append(f"🚧 Blocked ({len(blocked)}):")
        for t in blocked:
            due = f" due:{t.get('due', '')}" if t.get('due') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']}{epic}{due}  {t['title']}")
        lines.append("")

    # Overdue
    if overdue:
        lines.append(f"⚠️  Overdue ({len(overdue)}):")
        for t in overdue:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']} {pri}{epic} due:{t.get('due', '')}  {t['title']}")
        lines.append("")

    # Due today
    if due_today:
        lines.append(f"📍 Due today ({len(due_today)}):")
        for t in due_today:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']} {pri}{epic}  {t['title']}")
        lines.append("")

    # Due this week
    if due_week:
        lines.append(f"📆 This week ({len(due_week)}):")
        for t in due_week:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']} {pri}{epic} due:{t.get('due', '')}  {t['title']}")
        lines.append("")

    # My issues
    if my_issues:
        lines.append(f"🐛 My issues ({len(my_issues)}):")
        for i in my_issues:
            sev = f"[{i.get('severity', '').upper()}]" if i.get('severity') else ""
            lines.append(f"   {i['id']} {sev} {i['title']}")
        lines.append("")

    # Linked issues warning
    if linked_issues:
        lines.append(f"🔗 Linked open issues on active tasks: {len(linked_issues)}")
        lines.append("")

    # Next to pick up
    if ready and not in_progress:
        lines.append(f"⏳ Ready to start ({len(ready)}):")
        for t in ready[:5]:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            epic = f" [{t.get('epic', '').split('/')[-1]}]" if t.get('epic') else ""
            lines.append(f"   {t['id']} {pri}{epic}  {t['title']}")
        lines.append("")

    # Stats
    total = len(all_tasks)
    pct = round(len(done) / total * 100) if total else 0
    lines.append(f"📊 Stats: {len(done)}/{total} done ({pct}%) · {len(active_tasks)} active")

    if not active_tasks and not my_issues:
        lines.append("")
        lines.append("All clear! ☀️")

    click.echo("\n".join(lines))


@cli.command("standup")
@click.argument("owner")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--yesterday", "yesterday_date", default=None,
              help="Override 'yesterday' date (YYYY-MM-DD). Defaults to previous workday.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def standup_command(ctx: click.Context, owner: str, project: str | None,
                     epic: str | None, yesterday_date: str | None, json_output: bool) -> None:
    """Generate daily standup report: Yesterday, Today, Blockers."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today()

    # Determine "yesterday" — skip weekends
    if yesterday_date:
        yd = date.fromisoformat(yesterday_date)
    else:
        yd = today - timedelta(days=1)
        if yd.weekday() >= 5:  # Saturday or Sunday
            yd = today - timedelta(days=3 if today.weekday() == 0 else 2)
    yd_str = yd.isoformat()
    today_str = today.isoformat()

    # Get owner's tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    active = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]

    # Yesterday: completed + activity
    # Tasks done "yesterday" — check completed date or just done status
    done_yesterday = [t for t in all_tasks if t.get("status") == "done"]

    # Get yesterday's activity
    entries = collect_activity(root, limit=50, actor=owner, since=yd_str)
    yesterday_activity = [e for e in entries if e.get("date") == yd_str]

    # Today: in progress + due today + due this week
    in_progress = [t for t in active if t.get("status") == "in_progress"]
    due_today = [t for t in active if t.get("due") == today_str]
    within_3 = (today + timedelta(days=3)).isoformat()
    due_soon = [t for t in active
                if t.get("due") and today_str < t.get("due", "") <= within_3
                and t not in due_today]

    # Blockers: blocked tasks
    blocked = [t for t in active if t.get("status") == "blocked"]

    # My open issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    my_issues = [i for i in all_issues
                 if i.get("owner") == owner and i.get("status") not in ("done", "wontfix")]

    if json_output:
        data = {
            "owner": owner,
            "date": today_str,
            "yesterday": {
                "date": yd_str,
                "completed": [{"id": t["id"], "title": t["title"]} for t in done_yesterday],
                "activity": [{"entity_type": e["entity_type"], "entity_id": e["entity_id"],
                              "action": e["action"]} for e in yesterday_activity],
            },
            "today": {
                "in_progress": [{"id": t["id"], "title": t["title"], "due": t.get("due", "")} for t in in_progress],
                "due_today": [{"id": t["id"], "title": t["title"], "priority": t.get("priority", "")} for t in due_today],
                "due_soon": [{"id": t["id"], "title": t["title"], "due": t.get("due", "")} for t in due_soon],
            },
            "blockers": [{"id": t["id"], "title": t["title"]} for t in blocked],
            "issues": [{"id": i["id"], "title": i["title"], "severity": i.get("severity", "")} for i in my_issues],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🗣️  Standup: @{owner}")
    lines.append(f"   {today_str}")
    lines.append("")

    # Yesterday
    lines.append(f"**Yesterday ({yd_str}):**")
    if done_yesterday:
        for t in done_yesterday:
            lines.append(f"  - ✅ Completed: {t['id']} — {t['title']}")
    if yesterday_activity:
        for e in yesterday_activity:
            icon = {"task": "📋", "issue": "🐛", "milestone": "🏁", "inbox": "📥",
                    "epic": "🎯", "project": "📦", "spec": "📐", "plan": "📋"}.get(e["entity_type"], "📄")
            lines.append(f"  - {icon} {e['action']}: {e['entity_id']} — {e['entity_title']}")
    if not done_yesterday and not yesterday_activity:
        lines.append(f"  - (no recorded activity)")
    lines.append("")

    # Today
    lines.append("**Today:**")
    if in_progress:
        for t in in_progress:
            due = f" (due: {t.get('due', '')})" if t.get('due') else ""
            lines.append(f"  - 🔧 {t['id']} — {t['title']}{due}")
    if due_today:
        for t in due_today:
            pri = f" [{t.get('priority', '').upper()}]" if t.get('priority') else ""
            lines.append(f"  - 📍{pri} {t['id']} — {t['title']}")
    if due_soon and not in_progress and not due_today:
        for t in due_soon[:3]:
            pri = f" [{t.get('priority', '').upper()}]" if t.get('priority') else ""
            lines.append(f"  - 📆{pri} {t['id']} — {t['title']} (due: {t.get('due', '')})")
    if not in_progress and not due_today and not due_soon:
        # Suggest picking up next task
        next_list = next_tasks(root, owner=owner, epic=epic, project=project, limit=3)
        if next_list:
            lines.append("  - 💡 Suggest picking up:")
            for t in next_list:
                lines.append(f"    - {t['id']} — {t['title']}")
        else:
            lines.append("  - (nothing planned)")
    lines.append("")

    # Blockers
    lines.append("**Blockers:**")
    if blocked:
        for t in blocked:
            lines.append(f"  - 🚧 {t['id']} — {t['title']}")
    if my_issues:
        for i in my_issues:
            sev = f" [{i.get('severity', '').upper()}]" if i.get('severity') else ""
            lines.append(f"  - 🐛{sev} {i['id']} — {i['title']}")
    if not blocked and not my_issues:
        lines.append("  - None ✨")

    click.echo("\n".join(lines))


@cli.command("weekly")
@click.option("--project", default=None, help="Show weekly review for a specific project.")
@click.option("--epic", default=None, help="Show weekly review for a specific epic.")
@click.option("--owner", default=None, help="Show weekly review for a specific owner.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def weekly_command(ctx: click.Context, project: str | None, epic: str | None,
                     owner: str | None, json_output: bool) -> None:
    """Weekly review: completed this week, upcoming, and activity."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    week_start_str = week_start.isoformat()
    week_end_str = week_end.isoformat()
    today_str = today.isoformat()

    # Collect tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    done_this_week = [t for t in all_tasks
                      if t.get("status") == "done"
                      and t.get("completed")
                      and week_start_str <= t["completed"] <= week_end_str]
    # Fallback: if no completed date, check activity log
    if not done_this_week:
        done_this_week = [t for t in all_tasks if t.get("status") == "done"]

    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]
    due_this_week = [t for t in active_tasks
                     if t.get("due") and week_start_str <= t["due"] <= week_end_str]
    overdue = [t for t in active_tasks if t.get("due") and t["due"] < today_str]

    # Collect issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    closed_this_week = [i for i in all_issues if i.get("status") in ("done", "wontfix")]
    open_issues = [i for i in all_issues if i.get("status") not in ("done", "wontfix")]

    # Activity this week
    entries = collect_activity(root, limit=50, project=project, epic=epic,
                                since=week_start_str)

    # Milestones
    milestones = list_milestones(root, epic_ref=epic, project_ref=project)
    upcoming_milestones = sorted(
        [m for m in milestones if m.get("date") and m["date"] >= today_str and m.get("status") != "done"],
        key=lambda m: m.get("date", "")
    )[:3]

    if json_output:
        data = {
            "week": {"start": week_start_str, "end": week_end_str},
            "tasks": {
                "done_this_week": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")} for t in done_this_week],
                "due_this_week": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "owner": t.get("owner", "")} for t in due_this_week],
                "overdue": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""), "owner": t.get("owner", "")} for t in overdue],
                "active": len(active_tasks),
            },
            "issues": {
                "closed_this_week": len(closed_this_week),
                "open": len(open_issues),
            },
            "activity_count": len(entries),
            "upcoming_milestones": [{"title": m["title"], "date": m["date"]} for m in upcoming_milestones],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"📅 Weekly Review — {week_start_str} to {week_end_str}")
    lines.append("")

    # Completed
    lines.append(f"✅ Completed this week ({len(done_this_week)}):")
    if done_this_week:
        for t in done_this_week:
            owner_str = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']}{owner_str}  {t['title']}")
    else:
        lines.append("   (none)")
    lines.append("")

    # Due this week
    lines.append(f"📆 Due this week ({len(due_this_week)}):")
    if due_this_week:
        for t in due_this_week:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            owner_str = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {pri}{owner_str} due:{t.get('due', '')}  {t['title']}")
    else:
        lines.append("   (none)")
    lines.append("")

    # Overdue
    if overdue:
        lines.append(f"⚠️  Overdue ({len(overdue)}):")
        for t in overdue:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            owner_str = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"   {t['id']} {pri}{owner_str} due:{t.get('due', '')}  {t['title']}")
        lines.append("")

    # Issues
    lines.append(f"🐛 Issues: {len(open_issues)} open, {len(closed_this_week)} closed this week")
    lines.append("")

    # Activity
    lines.append(f"📝 Activity: {len(entries)} entries this week")
    lines.append("")

    # Upcoming milestones
    if upcoming_milestones:
        lines.append("🏁 Upcoming milestones:")
        for m in upcoming_milestones:
            lines.append(f"   {m['date']}  {m['title']}")
        lines.append("")

    # Summary
    total = len(all_tasks)
    done = len([t for t in all_tasks if t.get("status") == "done"])
    pct = round(done / total * 100) if total else 0
    lines.append(f"📊 Progress: {done}/{total} tasks done ({pct}%)")

    click.echo("\n".join(lines))


@cli.command("release")
@click.option("--milestone", "milestone_ref", default=None, help="Milestone to generate release notes for.")
@click.option("--since", default=None, help="Include items completed since YYYY-MM-DD.")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def release_command(ctx: click.Context, milestone_ref: str | None, since: str | None,
                     project: str | None, epic: str | None, json_output: bool) -> None:
    """Generate release notes from completed tasks and closed issues."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()

    # Determine the "since" date
    since_date = since
    if not since_date and milestone_ref:
        milestones = list_milestones(root, epic_ref=epic, project_ref=project)
        for m in milestones:
            if m.get("id") == milestone_ref or milestone_ref in m.get("path", ""):
                since_date = m.get("date")
                break
    if not since_date:
        since_date = (date.today() - timedelta(days=7)).isoformat()

    # Collect completed tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project)
    completed_tasks = [t for t in all_tasks if t.get("status") == "done"]

    # Collect closed issues
    all_issues = list_issues(root, epic_ref=epic, project_ref=project)
    closed_issues = [i for i in all_issues if i.get("status") in ("done", "wontfix")]

    # Group tasks by owner
    from collections import defaultdict
    tasks_by_owner: dict[str, list] = defaultdict(list)
    for t in completed_tasks:
        owner = t.get("owner") or "unassigned"
        tasks_by_owner[owner].append(t)

    if json_output:
        data = {
            "generated": today,
            "since": since_date,
            "milestone": milestone_ref,
            "completed_tasks": [
                {"id": t["id"], "title": t["title"], "owner": t.get("owner", ""),
                 "priority": t.get("priority", ""), "epic": t.get("epic", "")}
                for t in completed_tasks
            ],
            "closed_issues": [
                {"id": i["id"], "title": i["title"], "severity": i.get("severity", ""),
                 "owner": i.get("owner", ""), "epic": i.get("epic", "")}
                for i in closed_issues
            ],
            "stats": {
                "tasks_completed": len(completed_tasks),
                "issues_closed": len(closed_issues),
                "by_owner": {owner: len(tasks) for owner, tasks in tasks_by_owner.items()},
            },
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🚀 Release Notes")
    lines.append(f"   Generated: {today}")
    lines.append(f"   Since: {since_date}")
    if milestone_ref:
        lines.append(f"   Milestone: {milestone_ref}")
    lines.append("")

    # Summary
    lines.append(f"📊 Summary")
    lines.append(f"   ✅ {len(completed_tasks)} tasks completed")
    lines.append(f"   🐛 {len(closed_issues)} issues closed")
    lines.append("")

    # Completed tasks
    if completed_tasks:
        lines.append(f"✅ Completed Tasks ({len(completed_tasks)})")
        lines.append("")
        for owner in sorted(tasks_by_owner.keys()):
            tasks = tasks_by_owner[owner]
            lines.append(f"  @{owner} ({len(tasks)}):")
            for t in tasks:
                pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
                lines.append(f"    - {t['id']} {pri} {t['title']}")
            lines.append("")

    # Closed issues
    if closed_issues:
        lines.append(f"🐛 Closed Issues ({len(closed_issues)})")
        lines.append("")
        for i in closed_issues:
            sev = f"[{i.get('severity', '').upper()}]" if i.get('severity') else ""
            owner = f"@{i.get('owner', '')}" if i.get('owner') else ""
            lines.append(f"  - {i['id']} {sev}{owner} {i['title']}")
        lines.append("")

    # Contributors
    if tasks_by_owner:
        lines.append(f"👥 Contributors")
        for owner in sorted(tasks_by_owner.keys(), key=lambda o: -len(tasks_by_owner[o])):
            lines.append(f"   @{owner}: {len(tasks_by_owner[owner])} tasks")
        lines.append("")

    click.echo("\n".join(lines))


@cli.command("due-report")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--include-done", is_flag=True, help="Include done tasks.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def due_report_command(ctx: click.Context, project: str | None, epic: str | None,
                        owner: str | None, include_done: bool, json_output: bool) -> None:
    """Report tasks grouped by due date buckets."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today()
    today_str = today.isoformat()
    week_end = (today + timedelta(days=7)).isoformat()
    next_week_start = (today + timedelta(days=8)).isoformat()
    next_week_end = (today + timedelta(days=14)).isoformat()
    month_end = (today + timedelta(days=30)).isoformat()

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    if not include_done:
        all_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]

    # Buckets
    overdue = []
    due_today = []
    this_week = []
    next_week = []
    this_month = []
    later = []
    no_due = []

    for t in all_tasks:
        due = t.get("due", "")
        if not due:
            no_due.append(t)
        elif due < today_str:
            overdue.append(t)
        elif due == today_str:
            due_today.append(t)
        elif due <= week_end:
            this_week.append(t)
        elif due <= next_week_end:
            next_week.append(t)
        elif due <= month_end:
            this_month.append(t)
        else:
            later.append(t)

    buckets = [
        ("Overdue", overdue, "⚠️"),
        ("Due today", due_today, "📍"),
        ("This week", this_week, "📆"),
        ("Next week", next_week, "📅"),
        ("This month", this_month, "🗓️"),
        ("Later", later, "⏳"),
        ("No due date", no_due, "❓"),
    ]

    if json_output:
        data = {
            "generated": today_str,
            "total": len(all_tasks),
            "buckets": {
                name: {
                    "count": len(tasks),
                    "tasks": [{"id": t["id"], "title": t["title"], "due": t.get("due", ""),
                               "owner": t.get("owner", ""), "priority": t.get("priority", ""),
                               "status": t.get("status", "")} for t in tasks],
                }
                for name, tasks, _ in buckets
            },
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"📋 Due Report ({len(all_tasks)} tasks)")
    lines.append(f"   {today_str}")
    lines.append("")

    for name, tasks, icon in buckets:
        if not tasks and name in ("Later",):
            continue
        lines.append(f"{icon} {name} ({len(tasks)}):")
        if not tasks:
            lines.append("   (none)")
        else:
            for t in sorted(tasks, key=lambda x: (x.get("due", "") or "9999-99-99", x.get("priority", ""))):
                pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
                owner_str = f" @{t.get('owner', '')}" if t.get('owner') else ""
                due_str = f" due:{t.get('due', '')}" if t.get('due') else ""
                status = f" [{t.get('status', '')}]" if t.get('status') not in ('created', 'ready') else ""
                lines.append(f"   {t['id']} {pri}{owner_str}{due_str}{status}  {t['title']}")
        lines.append("")

    # Summary stats
    total_with_due = len(all_tasks) - len(no_due)
    if total_with_due > 0:
        on_time = len(due_today) + len(this_week) + len(next_week) + len(this_month) + len(later)
        lines.append(f"💡 {len(overdue)} overdue · {on_time} on schedule · {len(no_due)} no due date")

    click.echo("\n".join(lines))


@cli.command("priority-report")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--include-done", is_flag=True, help="Include done tasks.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def priority_report_command(ctx: click.Context, project: str | None, epic: str | None,
                             owner: str | None, include_done: bool, json_output: bool) -> None:
    """Report tasks grouped by priority with status breakdowns."""
    from collections import defaultdict
    root = find_repo_root(_cwd_from_context(ctx))

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    if not include_done:
        all_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]

    # Group by priority
    by_priority: dict[str, list] = defaultdict(list)
    for t in all_tasks:
        pri = t.get("priority") or "unspecified"
        by_priority[pri].append(t)

    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unspecified": 4}
    sorted_priorities = sorted(by_priority.keys(), key=lambda p: PRIORITY_ORDER.get(p, 99))

    if json_output:
        data = {
            "total": len(all_tasks),
            "by_priority": {
                pri: {
                    "count": len(tasks),
                    "by_status": {
                        status: len([t for t in tasks if t.get("status") == status])
                        for status in sorted(set(t.get("status", "unknown") for t in tasks))
                    },
                    "tasks": [{"id": t["id"], "title": t["title"], "status": t.get("status", ""),
                               "owner": t.get("owner", ""), "due": t.get("due", "")} for t in tasks],
                }
                for pri, tasks in by_priority.items()
            },
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"⚡ Priority Report ({len(all_tasks)} tasks)")
    lines.append("")

    max_count = max((len(tasks) for tasks in by_priority.values()), default=1)
    chart_width = 20

    for pri in sorted_priorities:
        tasks = by_priority[pri]
        count = len(tasks)
        bar_len = int(count / max(max_count, 1) * chart_width)
        bar = "█" * bar_len

        # Status breakdown
        statuses = defaultdict(int)
        for t in tasks:
            statuses[t.get("status", "unknown")] += 1
        status_str = ", ".join(f"{s}: {c}" for s, c in sorted(statuses.items()))

        emoji = {"critical": "🔥", "high": "🔴", "medium": "🟡", "low": "🟢", "unspecified": "❓"}.get(pri, "❓")
        lines.append(f"{emoji} {pri.upper():12s} {bar} {count}")
        lines.append(f"   {status_str}")

        # Show overdue critical/high
        overdue = [t for t in tasks if t.get("due") and t["due"] < str(__import__("datetime").date.today())]
        if overdue and pri in ("critical", "high"):
            lines.append(f"   ⚠️  {len(overdue)} overdue:")
            for t in overdue[:3]:
                lines.append(f"     {t['id']} due:{t.get('due', '')} {t['title']}")

        lines.append("")

    click.echo("\n".join(lines))


@cli.command("blocked-report")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def blocked_report_command(ctx: click.Context, project: str | None, epic: str | None,
                            owner: str | None, json_output: bool) -> None:
    """Report blocked tasks with their dependencies and linked issues."""
    from datetime import date
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    blocked = [t for t in all_tasks if t.get("status") == "blocked"]

    # For each blocked task, check dependencies
    blocked_data = []
    for t in sorted(blocked, key=lambda x: (x.get("due", "") or "9999-99-99", x.get("priority", ""))):
        deps = t.get("depends_on") or []
        soft_deps = t.get("soft_depends_on") or []
        known_issues = t.get("known_issues") or []
        is_overdue = t.get("due") and t["due"] < today

        # Check if hard deps are done
        dep_statuses = []
        for dep in deps:
            dep_task = None
            try:
                dep_tasks = list_tasks(root)
                for dt in dep_tasks:
                    if dt.get("id") == dep or dep in dt.get("path", ""):
                        dep_task = dt
                        break
            except Exception:
                pass
            if dep_task:
                dep_statuses.append(f"{dep} ({dep_task.get('status', '?')})")
            else:
                dep_statuses.append(f"{dep} (not found)")

        blocked_data.append({
            "id": t["id"],
            "title": t["title"],
            "owner": t.get("owner", ""),
            "due": t.get("due", ""),
            "priority": t.get("priority", ""),
            "overdue": is_overdue,
            "depends_on": dep_statuses,
            "soft_depends_on": list(soft_deps),
            "known_issues": list(known_issues),
            "epic": t.get("epic", ""),
        })

    if json_output:
        click.echo(json.dumps(blocked_data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🚧 Blocked Tasks Report ({len(blocked)})")
    lines.append("")

    if not blocked:
        lines.append("No blocked tasks. All clear! ✨")
        click.echo("\n".join(lines))
        return

    overdue_blocked = [b for b in blocked_data if b["overdue"]]
    if overdue_blocked:
        lines.append(f"⚠️  Overdue & blocked: {len(overdue_blocked)}")
        lines.append("")

    for b in blocked_data:
        overdue_icon = " ⚠️" if b["overdue"] else ""
        pri = f"[{b['priority'].upper()}]" if b["priority"] else ""
        owner = f" @{b['owner']}" if b["owner"] else ""
        due = f" due:{b['due']}" if b["due"] else ""
        epic = f" [{b['epic'].split('/')[-1]}]" if b["epic"] else ""
        lines.append(f"  🚧 {b['id']} {pri}{owner}{due}{epic}{overdue_icon}  {b['title']}")

        if b["depends_on"]:
            lines.append(f"     Hard deps: {', '.join(b['depends_on'])}")
        if b["soft_depends_on"]:
            lines.append(f"     Soft deps: {', '.join(b['soft_depends_on'])}")
        if b["known_issues"]:
            lines.append(f"     Known issues: {', '.join(b['known_issues'])}")

        if not b["depends_on"] and not b["soft_depends_on"] and not b["known_issues"]:
            lines.append(f"     (no dependencies or known issues listed — may need triage)")

        lines.append("")

    # By owner
    from collections import defaultdict
    by_owner: dict[str, int] = defaultdict(int)
    for b in blocked_data:
        o = b["owner"] or "unassigned"
        by_owner[o] += 1
    if len(by_owner) > 1:
        lines.append("By owner:")
        for o in sorted(by_owner.keys(), key=lambda x: -by_owner[x]):
            lines.append(f"  @{o}: {by_owner[o]}")

    click.echo("\n".join(lines))


@cli.command("roadmap")
@click.option("--project", default=None, help="Show roadmap for a specific project.")
@click.option("--epic", default=None, help="Show roadmap for a specific epic.")
@click.option("--limit", default=10, type=click.IntRange(min=1), help="Limit milestones shown.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def roadmap_command(ctx: click.Context, project: str | None, epic: str | None,
                     limit: int, json_output: bool) -> None:
    """Show upcoming milestones with task progress."""
    from datetime import date
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today().isoformat()

    milestones = list_milestones(root, epic_ref=epic, project_ref=project)
    # Filter to upcoming/active milestones and sort by date
    upcoming = sorted(
        [m for m in milestones if m.get("date") and m.get("status") != "done"],
        key=lambda m: m.get("date", "")
    )[:limit]

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project)

    milestone_data = []
    for m in upcoming:
        epic_path = m.get("epic", "")
        # Get tasks for this milestone's epic
        epic_tasks = [t for t in all_tasks if t.get("epic") == epic_path]
        total = len(epic_tasks)
        done = len([t for t in epic_tasks if t.get("status") == "done"])
        in_progress = len([t for t in epic_tasks if t.get("status") == "in_progress"])
        blocked = len([t for t in epic_tasks if t.get("status") == "blocked"])
        pct = round(done / total * 100) if total else 0

        # Progress bar
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        milestone_data.append({
            "id": m.get("id", ""),
            "title": m.get("title", ""),
            "date": m.get("date", ""),
            "status": m.get("status", ""),
            "epic": epic_path,
            "tasks": {"total": total, "done": done, "in_progress": in_progress, "blocked": blocked},
            "progress": pct,
            "bar": bar,
        })

    if json_output:
        data = {
            "generated": today,
            "milestones": [
                {
                    "id": m["id"], "title": m["title"], "date": m["date"],
                    "status": m["status"], "epic": m["epic"],
                    "progress": m["progress"], "tasks": m["tasks"],
                }
                for m in milestone_data
            ],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🗺️  Roadmap")
    lines.append(f"   {today}")
    lines.append("")

    if not milestone_data:
        lines.append("No upcoming milestones.")
        click.echo("\n".join(lines))
        return

    for m in milestone_data:
        days_away = ""
        if m["date"]:
            try:
                from datetime import date as _date
                delta = (_date.fromisoformat(m["date"]) - _date.fromisoformat(today)).days
                if delta > 0:
                    days_away = f" (in {delta}d)"
                elif delta == 0:
                    days_away = " (today)"
                else:
                    days_away = f" ({-delta}d overdue)"
            except ValueError:
                pass

        epic_slug = m["epic"].split("/")[-1] if "/" in m["epic"] else m["epic"]
        tasks = m["tasks"]
        lines.append(f"  🏁 {m['title']} — {m['date']}{days_away}")
        lines.append(f"     {m['status']:12s} [{epic_slug}]")
        lines.append(f"     {m['bar']} {m['progress']}%")
        lines.append(f"     📋 {tasks['total']} tasks: ✅ {tasks['done']} done, 🔧 {tasks['in_progress']} in progress, 🚧 {tasks['blocked']} blocked")
        lines.append("")

    # Overall stats
    total_tasks = len(all_tasks)
    done_tasks = len([t for t in all_tasks if t.get("status") == "done"])
    overall_pct = round(done_tasks / total_tasks * 100) if total_tasks else 0
    lines.append(f"📊 Overall: {done_tasks}/{total_tasks} tasks done ({overall_pct}%)")

    click.echo("\n".join(lines))


@cli.command("export")
@click.option("--output", "-o", default=None, help="Write to file instead of stdout.")
@click.option("--format", "fmt", default="json", type=click.Choice(("json", "csv"), case_sensitive=False),
              help="Output format (default: json). CSV outputs tasks and issues as separate CSV blocks.")
@click.option("--project", default=None, help="Export only a specific project.")
@click.option("--epic", default=None, help="Export only a specific epic (path or slug).")
@click.pass_context
def export_command(ctx: click.Context, output: str | None, fmt: str,
                    project: str | None, epic: str | None) -> None:
    """Export all project data as JSON or CSV."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = export_repo(root, project=project, epic=epic)

    if fmt == "csv":
        rendered = _format_export_csv(data)
    else:
        rendered = format_export(data)

    if output:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = root / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        try:
            click.echo(output_path.relative_to(root).as_posix())
        except ValueError:
            click.echo(str(output_path))
    else:
        click.echo(rendered)


@cli.command("burndown")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--start", default=None, help="Start date YYYY-MM-DD (default: earliest task created).")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default: today).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def burndown_command(ctx: click.Context, project: str | None, epic: str | None,
                      owner: str | None, start: str | None, end: str | None,
                      json_output: bool) -> None:
    """Generate burndown chart data (remaining tasks over time)."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today()

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)

    if not all_tasks:
        if json_output:
            click.echo("[]")
        else:
            click.echo("No tasks found.")
        return

    # Determine date range
    created_dates = [t.get("created") for t in all_tasks if t.get("created")]
    if start:
        start_date = date.fromisoformat(start)
    elif created_dates:
        start_date = date.fromisoformat(min(created_dates))
    else:
        start_date = today - timedelta(days=30)

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = today

    # Generate daily data points
    data_points = []
    current = start_date
    while current <= end_date:
        current_str = current.isoformat()
        # Tasks created by this date
        total_created = len([t for t in all_tasks
                             if t.get("created") and t["created"] <= current_str])
        # Tasks done by this date (approximate: done status)
        # We don't have completed date, so use status == done as "done by now"
        # For historical accuracy, we'd need activity log; this is a snapshot
        done_count = len([t for t in all_tasks if t.get("status") == "done"])
        remaining = total_created - done_count if current == end_date else total_created

        data_points.append({
            "date": current_str,
            "total_created": total_created,
            "remaining": remaining,
            "done": done_count,
        })
        current += timedelta(days=1)

    if json_output:
        click.echo(json.dumps(data_points, ensure_ascii=False, indent=2))
        return

    # Text output: ASCII chart
    lines = []
    lines.append(f"📉 Burndown: {start_date.isoformat()} → {end_date.isoformat()}")
    lines.append(f"   Tasks: {len(all_tasks)} total")
    lines.append("")

    max_remaining = max(d["remaining"] for d in data_points) if data_points else 1
    chart_width = 40

    # Show every Nth day to fit
    step = max(1, len(data_points) // 15)
    shown = data_points[::step]
    if shown[-1] != data_points[-1]:
        shown.append(data_points[-1])

    for d in shown:
        bar_len = int(d["remaining"] / max(max_remaining, 1) * chart_width)
        bar = "█" * bar_len
        lines.append(f"  {d['date']}  {bar} {d['remaining']}")

    lines.append("")
    lines.append(f"💡 Start: {data_points[0]['remaining'] if data_points else 0} tasks")
    lines.append(f"💡 End:   {data_points[-1]['remaining'] if data_points else 0} tasks remaining")

    click.echo("\n".join(lines))


@cli.command("velocity")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--weeks", default=4, show_default=True, type=click.IntRange(min=1, max=52),
              help="Number of weeks to include.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def velocity_command(ctx: click.Context, project: str | None, epic: str | None,
                      owner: str | None, weeks: int, json_output: bool) -> None:
    """Show team velocity: tasks completed per week."""
    from datetime import date, timedelta
    root = find_repo_root(_cwd_from_context(ctx))
    today = date.today()

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    done_tasks = [t for t in all_tasks if t.get("status") == "done"]

    # Build weekly buckets (most recent last)
    # Week starts on Monday
    week_start = today - timedelta(days=today.weekday())
    weekly: dict[str, list] = {}
    for i in range(weeks - 1, -1, -1):
        ws = week_start - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        key = f"{ws.isoformat()}~{we.isoformat()}"
        weekly[key] = []

    # Assign done tasks to weeks (approximate: use created date as proxy,
    # since we don't have a completed date in the task dict)
    # Better: check activity log for "Completed" entries
    for t in done_tasks:
        created = t.get("created", "")
        if not created:
            continue
        try:
            cd = date.fromisoformat(created)
            for key in weekly:
                ws_str, we_str = key.split("~")
                if ws_str <= created <= we_str:
                    weekly[key].append(t)
                    break
        except ValueError:
            continue

    # Compute stats
    week_counts = [len(tasks) for tasks in weekly.values()]
    total_done = sum(week_counts)
    avg_velocity = round(total_done / weeks, 1) if weeks else 0

    if json_output:
        data = {
            "weeks": weeks,
            "total_done": total_done,
            "average_velocity": avg_velocity,
            "weekly": [
                {"week": key, "completed": len(tasks),
                 "tasks": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")} for t in tasks]}
                for key, tasks in weekly.items()
            ],
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"⚡ Velocity (last {weeks} weeks)")
    lines.append(f"   Total completed: {total_done}")
    lines.append(f"   Average: {avg_velocity} tasks/week")
    lines.append("")

    max_count = max(week_counts) if week_counts else 1
    chart_width = 30

    for key, tasks in weekly.items():
        ws_str, we_str = key.split("~")
        count = len(tasks)
        bar_len = int(count / max(max_count, 1) * chart_width)
        bar = "█" * bar_len
        lines.append(f"  {ws_str}  {bar} {count}")

    lines.append("")
    if week_counts and len(week_counts) >= 2:
        recent = week_counts[-1]
        prev = week_counts[-2] if len(week_counts) >= 2 else 0
        if prev > 0:
            delta = round((recent - prev) / prev * 100)
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            lines.append(f"📈 Trend: {arrow} {abs(delta)}% vs last week")

    click.echo("\n".join(lines))


@cli.command("sprint")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--owner", default=None, help="Filter by owner.")
@click.option("--start", "sprint_start", default=None, help="Sprint start date YYYY-MM-DD (default: today).")
@click.option("--length", default=14, show_default=True, type=click.IntRange(min=1, max=90),
              help="Sprint length in days.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def sprint_command(ctx: click.Context, project: str | None, epic: str | None,
                    owner: str | None, sprint_start: str | None, length: int,
                    json_output: bool) -> None:
    """Sprint planning view: tasks due within sprint window, capacity, and suggestions."""
    from datetime import date, timedelta
    from collections import defaultdict
    root = find_repo_root(_cwd_from_context(ctx))

    # Determine sprint window
    if sprint_start:
        start = date.fromisoformat(sprint_start)
    else:
        start = date.today()
    end = start + timedelta(days=length - 1)
    start_str = start.isoformat()
    end_str = end.isoformat()
    today = date.today().isoformat()

    # Get all tasks
    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project, owner=owner)
    active = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]

    # Tasks due within sprint
    in_sprint = [t for t in active
                 if t.get("due") and start_str <= t["due"] <= end_str]

    # Tasks already in progress
    in_progress = [t for t in in_sprint if t.get("status") == "in_progress"]

    # Tasks ready to start
    ready = [t for t in in_sprint if t.get("status") in ("ready", "created")]

    # Blocked tasks
    blocked = [t for t in in_sprint if t.get("status") == "blocked"]

    # Overdue (before sprint start)
    overdue = [t for t in active if t.get("due") and t["due"] < start_str]

    # By owner breakdown
    by_owner: dict[str, list] = defaultdict(list)
    for t in in_sprint:
        o = t.get("owner") or "unassigned"
        by_owner[o].append(t)

    # Capacity estimate (assume ~1 task per person per 2 days as rough)
    working_days = length
    capacity_per_person = max(1, working_days // 2)
    total_capacity = len(by_owner) * capacity_per_person

    # Suggestions: ready tasks not yet in sprint but could be pulled in
    not_in_sprint_ready = [t for t in active
                           if t.get("status") in ("ready", "created")
                           and (not t.get("due") or t["due"] > end_str)]

    if json_output:
        data = {
            "sprint": {"start": start_str, "end": end_str, "length_days": length},
            "tasks": {
                "in_sprint": len(in_sprint),
                "in_progress": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", ""),
                                 "due": t.get("due", ""), "priority": t.get("priority", "")}
                                for t in in_progress],
                "ready": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", ""),
                           "due": t.get("due", ""), "priority": t.get("priority", "")}
                          for t in ready],
                "blocked": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", "")}
                            for t in blocked],
                "overdue": [{"id": t["id"], "title": t["title"], "owner": t.get("owner", ""),
                             "due": t.get("due", "")} for t in overdue],
            },
            "by_owner": {
                owner: {"count": len(tasks), "capacity": capacity_per_person}
                for owner, tasks in sorted(by_owner.items())
            },
            "capacity": {
                "estimated": total_capacity,
                "committed": len(in_sprint),
                "available": max(0, total_capacity - len(in_sprint)),
            },
            "suggestions": {
                "pull_in": [{"id": t["id"], "title": t["title"], "priority": t.get("priority", "")}
                            for t in not_in_sprint_ready[:5]],
            },
        }
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    lines = []
    lines.append(f"🏃 Sprint: {start_str} → {end_str} ({length} days)")
    lines.append("")

    # Summary
    lines.append(f"📊 Sprint Summary")
    lines.append(f"   Tasks in sprint: {len(in_sprint)}")
    lines.append(f"   In progress: {len(in_progress)}")
    lines.append(f"   Ready: {len(ready)}")
    if blocked:
        lines.append(f"   Blocked: {len(blocked)}")
    if overdue:
        lines.append(f"   Overdue (carry-in): {len(overdue)}")
    lines.append("")

    # Capacity
    lines.append(f"👥 Capacity ({len(by_owner)} owners, ~{capacity_per_person} tasks/person)")
    lines.append(f"   Estimated capacity: {total_capacity} tasks")
    lines.append(f"   Committed: {len(in_sprint)}")
    avail = max(0, total_capacity - len(in_sprint))
    if avail > 0:
        lines.append(f"   Available: {avail} slots ↓")
    elif avail == 0:
        lines.append(f"   At capacity ✅")
    else:
        lines.append(f"   Overcommitted by {-avail} tasks ⚠️")
    lines.append("")

    # By owner
    if by_owner:
        lines.append("By owner:")
        for o in sorted(by_owner.keys()):
            tasks = by_owner[o]
            done = len([t for t in tasks if t.get("status") == "done"])
            lines.append(f"  @{o}: {len(tasks)} tasks")

    # In progress
    if in_progress:
        lines.append("")
        lines.append(f"🔧 In Progress ({len(in_progress)}):")
        for t in in_progress:
            due = f" due:{t.get('due', '')}" if t.get('due') else ""
            owner = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"  - {t['id']}{owner}{due}  {t['title']}")

    # Ready to start
    if ready:
        lines.append("")
        lines.append(f"⏳ Ready to Start ({len(ready)}):")
        for t in ready:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            due = f" due:{t.get('due', '')}" if t.get('due') else ""
            owner = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"  - {t['id']} {pri}{owner}{due}  {t['title']}")

    # Blocked
    if blocked:
        lines.append("")
        lines.append(f"🚧 Blocked ({len(blocked)}):")
        for t in blocked:
            owner = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"  - {t['id']}{owner}  {t['title']}")

    # Overdue
    if overdue:
        lines.append("")
        lines.append(f"⚠️  Overdue / Carry-in ({len(overdue)}):")
        for t in overdue:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            owner = f" @{t.get('owner', '')}" if t.get('owner') else ""
            lines.append(f"  - {t['id']} {pri}{owner} due:{t.get('due', '')}  {t['title']}")

    # Suggestions
    if not_in_sprint_ready and avail > 0:
        lines.append("")
        lines.append(f"💡 Suggest to pull in ({min(avail, len(not_in_sprint_ready))}):")
        for t in not_in_sprint_ready[:avail]:
            pri = f"[{t.get('priority', '').upper()}]" if t.get('priority') else ""
            lines.append(f"  + {t['id']} {pri} {t['title']}")

    click.echo("\n".join(lines))


@cli.command("tag-list")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--sort", "sort_by", default="count",
              type=click.Choice(("count", "name"), case_sensitive=False),
              help="Sort tags by count or name (default: count).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def tag_list_command(ctx: click.Context, project: str | None, epic: str | None,
                      sort_by: str, json_output: bool) -> None:
    """List all tags used across tasks with counts."""
    from collections import Counter
    root = find_repo_root(_cwd_from_context(ctx))

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project)
    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "wontfix")]

    tag_counter: Counter = Counter()
    tag_tasks: dict[str, list] = {}

    for t in all_tasks:
        tags = t.get("tags") or []
        for tag in tags:
            tag_str = str(tag)
            tag_counter[tag_str] += 1
            if tag_str not in tag_tasks:
                tag_tasks[tag_str] = []
            tag_tasks[tag_str].append(t)

    # Active-only counts
    active_tag_counter: Counter = Counter()
    for t in active_tasks:
        tags = t.get("tags") or []
        for tag in tags:
            active_tag_counter[str(tag)] += 1

    if sort_by == "name":
        sorted_tags = sorted(tag_counter.keys())
    else:
        sorted_tags = [t for t, _ in tag_counter.most_common()]

    if json_output:
        data = [
            {
                "tag": tag,
                "count": tag_counter[tag],
                "active_count": active_tag_counter.get(tag, 0),
                "tasks": [{"id": t["id"], "title": t["title"], "status": t.get("status", "")}
                          for t in tag_tasks.get(tag, [])],
            }
            for tag in sorted_tags
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not tag_counter:
        click.echo("No tags found.")
        return

    lines = []
    lines.append(f"🏷️  Tags ({len(tag_counter)} total)")
    lines.append("")

    max_count = max(tag_counter.values()) if tag_counter else 1
    chart_width = 20

    for tag in sorted_tags:
        count = tag_counter[tag]
        active = active_tag_counter.get(tag, 0)
        bar_len = int(count / max(max_count, 1) * chart_width)
        bar = "█" * bar_len
        lines.append(f"  {tag:20s} {bar} {count} total ({active} active)")

    lines.append("")
    lines.append(f"💡 {len(all_tasks)} tasks total, {len(active_tasks)} active")

    click.echo("\n".join(lines))


@cli.command("owner-list")
@click.option("--project", default=None, help="Filter by project.")
@click.option("--epic", default=None, help="Filter by epic.")
@click.option("--sort", "sort_by", default="active",
              type=click.Choice(("active", "total", "name", "done"), case_sensitive=False),
              help="Sort owners (default: active count).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def owner_list_command(ctx: click.Context, project: str | None, epic: str | None,
                        sort_by: str, json_output: bool) -> None:
    """List all task owners with their task counts."""
    from collections import defaultdict
    root = find_repo_root(_cwd_from_context(ctx))

    all_tasks = list_tasks(root, epic_ref=epic, project_ref=project)

    owner_stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "active": 0, "done": 0, "blocked": 0,
        "in_progress": 0, "overdue": 0,
    })

    from datetime import date
    today = date.today().isoformat()

    for t in all_tasks:
        owner = t.get("owner") or "unassigned"
        stats = owner_stats[owner]
        stats["total"] += 1
        status = t.get("status", "")
        if status == "done":
            stats["done"] += 1
        elif status == "blocked":
            stats["blocked"] += 1
            stats["active"] += 1
        elif status == "in_progress":
            stats["in_progress"] += 1
            stats["active"] += 1
        elif status not in ("done", "wontfix"):
            stats["active"] += 1
        if status not in ("done", "wontfix") and t.get("due") and t["due"] < today:
            stats["overdue"] += 1

    # Sort
    if sort_by == "name":
        sorted_owners = sorted(owner_stats.keys())
    elif sort_by == "total":
        sorted_owners = sorted(owner_stats.keys(), key=lambda o: -owner_stats[o]["total"])
    elif sort_by == "done":
        sorted_owners = sorted(owner_stats.keys(), key=lambda o: -owner_stats[o]["done"])
    else:  # active
        sorted_owners = sorted(owner_stats.keys(), key=lambda o: -owner_stats[o]["active"])

    if json_output:
        data = [
            {
                "owner": owner,
                "total": owner_stats[owner]["total"],
                "active": owner_stats[owner]["active"],
                "done": owner_stats[owner]["done"],
                "blocked": owner_stats[owner]["blocked"],
                "in_progress": owner_stats[owner]["in_progress"],
                "overdue": owner_stats[owner]["overdue"],
            }
            for owner in sorted_owners
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not owner_stats:
        click.echo("No task owners found.")
        return

    lines = []
    lines.append(f"👥 Task Owners ({len(owner_stats)})")
    lines.append("")

    max_active = max(s["active"] for s in owner_stats.values()) if owner_stats else 1
    chart_width = 20

    for owner in sorted_owners:
        s = owner_stats[owner]
        bar_len = int(s["active"] / max(max_active, 1) * chart_width)
        bar = "█" * bar_len
        lines.append(f"  @{owner:15s} {bar} active:{s['active']} total:{s['total']} done:{s['done']}")
        details = []
        if s["blocked"]:
            details.append(f"🚧 {s['blocked']}")
        if s["in_progress"]:
            details.append(f"🔧 {s['in_progress']}")
        if s["overdue"]:
            details.append(f"⚠️ {s['overdue']}")
        if details:
            lines.append(f"  {'':15s}  {' '.join(details)}")

    lines.append("")
    lines.append(f"💡 {len(all_tasks)} tasks total")

    click.echo("\n".join(lines))


def _format_export_csv(data: dict) -> str:
    """Format exported data as CSV with separate sections for tasks and issues."""
    import csv
    import io

    output = io.StringIO()

    # Tasks CSV
    tasks: list[dict] = []
    for proj in data.get("projects", []):
        for epic in proj.get("epics", []):
            for task in epic.get("tasks", []):
                row = {
                    "project": proj.get("slug", ""),
                    "epic": epic.get("slug", ""),
                    "id": task.get("id", ""),
                    "title": task.get("title", ""),
                    "status": task.get("status", ""),
                    "priority": task.get("priority", ""),
                    "owner": task.get("owner", ""),
                    "due": task.get("due", ""),
                    "created": task.get("created", ""),
                }
                tasks.append(row)

    if tasks:
        output.write("# Tasks\n")
        writer = csv.DictWriter(output, fieldnames=["project", "epic", "id", "title",
                                                     "status", "priority", "owner", "due", "created"])
        writer.writeheader()
        for t in tasks:
            writer.writerow(t)

    # Issues CSV
    issues: list[dict] = []
    for proj in data.get("projects", []):
        for epic in proj.get("epics", []):
            for issue in epic.get("issues", []):
                row = {
                    "project": proj.get("slug", ""),
                    "epic": epic.get("slug", ""),
                    "id": issue.get("id", ""),
                    "title": issue.get("title", ""),
                    "status": issue.get("status", ""),
                    "severity": issue.get("severity", ""),
                    "owner": issue.get("owner", ""),
                    "created": issue.get("created", ""),
                }
                issues.append(row)

    if issues:
        if tasks:
            output.write("\n")
        output.write("# Issues\n")
        writer = csv.DictWriter(output, fieldnames=["project", "epic", "id", "title",
                                                     "status", "severity", "owner", "created"])
        writer.writeheader()
        for i in issues:
            writer.writerow(i)

    return output.getvalue().rstrip()


@cli.command("import")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.pass_context
def import_command(ctx: click.Context, input_file: Path, force: bool) -> None:
    """Import project data from a JSON export file."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = load_export_file(input_file)
    created = import_repo(root, data, force=force)
    if not created:
        click.echo("Nothing to import — all entities already exist (use --force to overwrite).")
    else:
        for path in created:
            click.echo(path.relative_to(root).as_posix())
        click.echo(f"\nImported {len(created)} file(s).")


@cli.group("inbox")
def inbox_group() -> None:
    """Capture and triage project or epic inbox items."""


@inbox_group.command("add")
@click.option("--project", "project_slug", default=None)
@click.option("--epic", "epic_ref", default=None)
@click.option("--author", required=True)
@click.option("--title", required=True)
@click.option("--note", required=True)
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def inbox_add(
    ctx: click.Context,
    project_slug: str | None,
    epic_ref: str | None,
    author: str,
    title: str,
    note: str,
    dry_run: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        scope = epic_ref or project_slug or "(root)"
        click.echo(f"[DRY RUN] Would create inbox item in {scope}:")
        click.echo(f"  Title: {title}")
        click.echo(f"  Author: {author}")
        click.echo(f"  Note: {note}")
        return
    touched = add_inbox_item(root, project=project_slug, epic=epic_ref, author=author, title=title, note=note)
    _echo_touched(root, [touched])


@inbox_group.command("list")
@click.option("--project", "project_slug", default=None)
@click.option("--epic", "epic_ref", default=None)
@click.option("--status", default=None, type=click.Choice(("open", "resolved"), case_sensitive=False),
              help="Filter by inbox item status.")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "epic", "project"), case_sensitive=False),
              help="Group inbox items by status, epic, or project.")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "title", "status"), case_sensitive=False),
              help="Sort inbox items (default: created).")
@click.option("--created-since", default=None, help="Filter inbox items created on or after YYYY-MM-DD.")
@click.option("--created-before", default=None, help="Filter inbox items created before YYYY-MM-DD.")
@click.option("--created-today", is_flag=True, help="Show only inbox items created today.")
@click.option("--created-this-week", is_flag=True, help="Show only inbox items created this week.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--ids", "ids_only", is_flag=True, help="Output only entity IDs (one per line, for piping).")
@click.option("--count", "count_only", is_flag=True, help="Show only the count of matching inbox items.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.pass_context
def inbox_list(ctx: click.Context, project_slug: str | None, epic_ref: str | None,
               status: str | None, group_by: str | None, sort_by: str,
               created_since: str | None, created_before: str | None,
               created_today: bool, created_this_week: bool,
               limit: int | None,
               compact: bool, ids_only: bool, count_only: bool, csv_output: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    items = list_inbox_items(root, project=project_slug, epic=epic_ref, status=status)
    # Sort
    if sort_by == "title":
        items.sort(key=lambda i: i.title.lower())
    elif sort_by == "status":
        items.sort(key=lambda i: (0 if i.status == "open" else 1, i.title.lower()))
    # --created-today and --created-this-week shortcuts
    if created_today or created_this_week:
        from datetime import date, timedelta
        today = date.today()
        if created_today:
            today_str = today.isoformat()
            items = [i for i in items if i.created == today_str]
        elif created_this_week:
            week_start = today - timedelta(days=today.weekday())
            week_start_str = week_start.isoformat()
            items = [i for i in items if i.created and i.created >= week_start_str]
    # else: created (default order from list_inbox_items)
    if created_since:
        items = [i for i in items if i.created and i.created >= created_since]
    if created_before:
        items = [i for i in items if i.created and i.created < created_before]
    if ids_only:
        for item in items:
            click.echo(item.item_id)
        return
    if count_only:
        click.echo(f"{len(items)} inbox item{'s' if len(items) != 1 else ''}")
        return
    if limit:
        items = items[:limit]
    if csv_output:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["item_id", "title", "status", "epic", "path"])
        for item in items:
            rel = item.path.relative_to(root).as_posix()
            parts = rel.split("/")
            epic = f"projects/{parts[1]}/{parts[2]}" if len(parts) > 2 else ""
            writer.writerow([item.item_id, item.title, item.status, epic, rel])
        click.echo(output.getvalue(), nl=False)
        return
    if json_output:
        data = []
        for item in items:
            rel = item.path.relative_to(root).as_posix()
            parts = rel.split("/")
            epic = f"projects/{parts[1]}/{parts[2]}" if len(parts) > 2 else ""
            project = parts[1] if len(parts) > 1 else ""
            data.append({
                "item_id": item.item_id,
                "title": item.title,
                "status": item.status,
                "epic": epic,
                "project": project,
                "path": rel,
            })
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not items:
            click.echo("No inbox items.")
            return

        if group_by:
            from collections import defaultdict
            groups: dict[str, list] = defaultdict(list)
            for item in items:
                rel = item.path.relative_to(root).as_posix()
                parts = rel.split("/")
                if group_by == "epic":
                    key = f"projects/{parts[1]}/{parts[2]}" if len(parts) > 2 else "unknown"
                elif group_by == "project":
                    key = parts[1] if len(parts) > 1 else "unknown"
                else:
                    key = item.status
                groups[key].append(item)

            if group_by == "status":
                st_order = {"open": 0, "resolved": 1}
                sorted_keys = sorted(groups.keys(), key=lambda k: st_order.get(k, 99))
            else:
                sorted_keys = sorted(groups.keys())

            for key in sorted_keys:
                group_items = groups[key]
                display_key = key
                if group_by == "epic":
                    display_key = key.split("/")[-1] if "/" in key else key
                click.echo(f"\n{display_key.upper()} ({len(group_items)})")
                click.echo("─" * 60)
                for item in group_items:
                    click.echo(f"  {item.item_id:20s} {item.status:10s} {item.title}")
        else:
            for item in items:
                click.echo(f"{item.item_id} {item.status} {item.title}")


@inbox_group.command("resolve")
@click.argument("item_ref")
@click.option("--resolver", required=True)
@click.option("--note", required=True)
@click.pass_context
def inbox_resolve(ctx: click.Context, item_ref: str, resolver: str, note: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = resolve_inbox_item(root, item_ref=item_ref, resolver=resolver, note=note)
    _echo_touched(root, [touched])


@inbox_group.command("bulk-resolve")
@click.argument("item_refs", nargs=-1)
@click.option("--resolver", required=True)
@click.option("--note", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read inbox item IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def inbox_bulk_resolve(
    ctx: click.Context,
    item_refs: tuple[str, ...],
    resolver: str,
    note: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-resolve inbox items (e.g. IN-001 IN-002, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(item_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no inbox item IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would resolve {len(refs)} inbox item(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for item_ref in refs:
        try:
            path = resolve_inbox_item(root, item_ref=item_ref, resolver=resolver, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {item_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@inbox_group.command("show")
@click.argument("item_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def inbox_show(ctx: click.Context, item_ref: str, json_output: bool) -> None:
    """Show details of a single inbox item."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = show_entity(root, item_ref, "IN")
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Inbox"), nl=False)


@inbox_group.command("edit")
@click.argument("item_ref")
@click.option("--title", default=None, help="New inbox item title.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def inbox_edit(
    ctx: click.Context,
    item_ref: str,
    title: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on an inbox item."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = edit_inbox_item(
        root,
        item_ref=item_ref,
        actor=actor,
        title=title,
        note=note,
    )
    _echo_touched(root, [touched])


def _cwd_from_context(ctx: click.Context) -> Path:
    if ctx.obj and "cwd" in ctx.obj:
        return Path(ctx.obj["cwd"])
    return Path.cwd()


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _echo_touched(repo_root: Path, paths: list[Path]) -> None:
    for path in paths:
        click.echo(path.relative_to(repo_root).as_posix())


def _read_ids_from_file(source: str) -> list[str]:
    """Read entity IDs from a file path, or '-' for stdin. One ID per line."""
    import sys
    if source == "-":
        content = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_absolute():
            path = Path.cwd() / path
        content = path.read_text(encoding="utf-8")
    return [line.strip() for line in content.splitlines() if line.strip()]


def _relative_to_root(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix()


@cli.group("roster")
def roster_group() -> None:
    """Manage roster.yaml."""


@roster_group.command("add")
@click.option("--email", required=True)
@click.option("--shortname", required=True)
@click.option("--name", required=True)
@click.option("--uid", default=None)
@click.pass_context
def roster_add(ctx: click.Context, email: str, shortname: str, name: str, uid: str | None) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    roster = Roster.load(root / "roster.yaml")
    try:
        developer = roster.add(email=email, shortname=shortname, name=name, uid=uid)
    except ValueError as exc:
        raise TrailmindError(str(exc)) from exc
    roster.save()
    click.echo(f"Added {developer.email} as {developer.shortname} ({developer.uid})")


@roster_group.command("list")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tab-separated text.")
@click.pass_context
def roster_list(ctx: click.Context, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    roster = Roster.load(root / "roster.yaml")
    if json_output:
        data = [
            {
                "shortname": d.shortname,
                "email": d.email,
                "uid": d.uid,
                "name": d.name,
            }
            for d in roster.developers
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for developer in roster.developers:
            click.echo(f"{developer.shortname}\t{developer.email}\t{developer.uid}\t{developer.name}")


@cli.group("plan")
def plan_group() -> None:
    """Manage planning artifacts."""


@plan_group.command("breakdown")
@click.argument("plan_path")
@click.option("--epic", "epic_ref", required=True)
@click.option("--filer", required=True)
@click.option("--owner", required=True)
@click.option("--write", "write_changes", is_flag=True, help="Create task files.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.option("--force", is_flag=True, help="Allow duplicate generated tasks for the same source section.")
@click.pass_context
def plan_breakdown(
    ctx: click.Context,
    plan_path: str,
    epic_ref: str,
    filer: str,
    owner: str,
    write_changes: bool,
    json_output: bool,
    force: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    report = build_breakdown_report(
        root,
        plan_ref=plan_path,
        epic_ref=epic_ref,
        filer=filer,
        owner=owner,
        write=write_changes,
        force=force,
    )
    if json_output:
        click.echo(json.dumps(breakdown_report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        click.echo(format_breakdown_markdown(report), nl=False)


@plan_group.group("spec")
def spec_group() -> None:
    """Manage spec artifacts."""


@spec_group.command("init")
@click.option("--epic", "epic_ref", required=True)
@click.option("--title", required=True)
@click.option("--author", required=True)
@click.option("--scope", default=None)
@click.option("--status", default="draft-for-review", type=click.Choice(SPEC_STATUSES))
@click.pass_context
def spec_init(ctx: click.Context, epic_ref: str, title: str, author: str, scope: str | None, status: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = create_spec(
        root,
        epic_ref=epic_ref,
        title=title,
        author=author,
        scope=scope,
        status=status,
    )
    _echo_touched(root, [touched])


@spec_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, help="Filter by spec status.")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "title", "status"), case_sensitive=False),
              help="Sort specs (default: created).")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--count", "count_only", is_flag=True, help="Show only the count.")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def spec_list(ctx: click.Context, epic_ref: str | None, project_ref: str | None,
              status: str | None, sort_by: str, compact: bool, count_only: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    specs = list_specs(root, epic_ref=epic_ref, project_ref=project_ref, status=status)
    if count_only:
        click.echo(f"{len(specs)} spec{'s' if len(specs) != 1 else ''}")
        return
    # Sort
    SPEC_STATUS_ORDER = {"draft": 0, "draft-for-review": 1, "approved-for-spec": 2, "superseded": 3}
    if sort_by == "title":
        specs.sort(key=lambda s: s.title.lower())
    elif sort_by == "status":
        specs.sort(key=lambda s: (SPEC_STATUS_ORDER.get(s.status, 99), s.title.lower()))
    else:
        specs.sort(key=lambda s: s.created or "9999-99-99")
    if json_output:
        data = [
            {
                "path": s.path,
                "title": s.title,
                "status": s.status,
                "created": s.created,
                "scope": s.scope,
            }
            for s in specs
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not specs:
            click.echo("No specs found.")
            return
        for s in specs:
            if compact:
                scope_str = f" [{s.scope}]" if s.scope else ""
                click.echo(f"{s.status:30s} {s.title}{scope_str}")
            else:
                scope_str = f" [{s.scope}]" if s.scope else ""
                click.echo(f"{s.status:30s} {s.title}{scope_str}")
                click.echo(f"  {s.path}")


@spec_group.command("show")
@click.argument("spec_ref")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def spec_show(ctx: click.Context, spec_ref: str, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    path = _resolve_any_doc(root, spec_ref, "spec")
    text = path.read_text(encoding="utf-8")
    info = parse_spec_info(text, path=path.relative_to(root).as_posix())
    if json_output:
        click.echo(json.dumps({
            "path": info.path,
            "title": info.title,
            "status": info.status,
            "created": info.created,
            "scope": info.scope,
            "project": info.project,
            "epic": info.epic,
            "linked_plans": info.linked_plans,
        }, ensure_ascii=False, indent=2))
    else:
        click.echo(f"# {info.title}")
        click.echo(f"Status: {info.status}")
        if info.created:
            click.echo(f"Created: {info.created}")
        if info.scope:
            click.echo(f"Scope: {info.scope}")
        click.echo(f"Path: {info.path}")
        if info.linked_plans:
            click.echo(f"Linked plans: {', '.join(info.linked_plans)}")


@spec_group.command("set-status")
@click.argument("spec_ref")
@click.option("--status", required=True, type=click.Choice(SPEC_STATUSES))
@click.option("--actor", required=True)
@click.pass_context
def spec_set_status_cmd(ctx: click.Context, spec_ref: str, status: str, actor: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_spec_status(root, spec_ref=spec_ref, status=status, actor=actor)
    _echo_touched(root, [touched])


@plan_group.command("init")
@click.option("--epic", "epic_ref", required=True)
@click.option("--title", required=True)
@click.option("--author", required=True)
@click.option("--spec", "spec_ref", default=None)
@click.option("--scope", default=None)
@click.option("--status", default="draft", type=click.Choice(PLAN_STATUSES))
@click.pass_context
def plan_init_cmd(ctx: click.Context, epic_ref: str, title: str, author: str, spec_ref: str | None, scope: str | None, status: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = create_plan(
        root,
        epic_ref=epic_ref,
        title=title,
        author=author,
        spec_ref=spec_ref,
        scope=scope,
        status=status,
    )
    _echo_touched(root, [touched])


@plan_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, help="Filter by plan status.")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "title", "status"), case_sensitive=False),
              help="Sort plans (default: created).")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--count", "count_only", is_flag=True, help="Show only the count.")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def plan_list_cmd(ctx: click.Context, epic_ref: str | None, project_ref: str | None,
                  status: str | None, sort_by: str, compact: bool, count_only: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    plans = list_plans(root, epic_ref=epic_ref, project_ref=project_ref, status=status)
    if count_only:
        click.echo(f"{len(plans)} plan{'s' if len(plans) != 1 else ''}")
        return
    # Sort
    PLAN_STATUS_ORDER = {"draft": 0, "approved": 1, "in-progress": 2, "completed": 3, "superseded": 4}
    if sort_by == "title":
        plans.sort(key=lambda p: p.title.lower())
    elif sort_by == "status":
        plans.sort(key=lambda p: (PLAN_STATUS_ORDER.get(p.status, 99), p.title.lower()))
    else:
        plans.sort(key=lambda p: p.created or "9999-99-99")
    if json_output:
        data = [
            {
                "path": p.path,
                "title": p.title,
                "status": p.status,
                "created": p.created,
                "scope": p.scope,
                "linked_spec": p.linked_spec,
                "generated_tasks": p.generated_tasks,
            }
            for p in plans
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not plans:
            click.echo("No plans found.")
            return
        for p in plans:
            if compact:
                scope_str = f" [{p.scope}]" if p.scope else ""
                click.echo(f"{p.status:15s} {p.title}{scope_str}")
            else:
                scope_str = f" [{p.scope}]" if p.scope else ""
                click.echo(f"{p.status:15s} {p.title}{scope_str}")
                click.echo(f"  {p.path}")


@plan_group.command("show")
@click.argument("plan_ref")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def plan_show_cmd(ctx: click.Context, plan_ref: str, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    path = _resolve_any_doc(root, plan_ref, "plan")
    text = path.read_text(encoding="utf-8")
    info = parse_plan_info(text, path=path.relative_to(root).as_posix())
    if json_output:
        click.echo(json.dumps({
            "path": info.path,
            "title": info.title,
            "status": info.status,
            "created": info.created,
            "scope": info.scope,
            "project": info.project,
            "epic": info.epic,
            "linked_spec": info.linked_spec,
            "generated_tasks": info.generated_tasks,
        }, ensure_ascii=False, indent=2))
    else:
        click.echo(f"# {info.title}")
        click.echo(f"Status: {info.status}")
        if info.created:
            click.echo(f"Created: {info.created}")
        if info.scope:
            click.echo(f"Scope: {info.scope}")
        click.echo(f"Path: {info.path}")
        if info.linked_spec:
            click.echo(f"Linked spec: {info.linked_spec}")
        if info.generated_tasks:
            click.echo(f"Generated tasks: {', '.join(info.generated_tasks)}")


@plan_group.command("set-status")
@click.argument("plan_ref")
@click.option("--status", required=True, type=click.Choice(PLAN_STATUSES))
@click.option("--actor", required=True)
@click.pass_context
def plan_set_status_cmd(ctx: click.Context, plan_ref: str, status: str, actor: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_plan_status(root, plan_ref=plan_ref, status=status, actor=actor)
    _echo_touched(root, [touched])


@plan_group.command("link-spec")
@click.option("--plan", "plan_ref", required=True)
@click.option("--spec", "spec_ref", required=True)
@click.pass_context
def plan_link_spec_cmd(ctx: click.Context, plan_ref: str, spec_ref: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = link_plan_spec(root, plan_ref=plan_ref, spec_ref=spec_ref)
    _echo_touched(root, touched)


@plan_group.command("status")
@click.option("--epic", "epic_ref", required=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def plan_status_cmd(ctx: click.Context, epic_ref: str, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    status = build_planning_status(root, epic_ref=epic_ref)
    if json_output:
        click.echo(json.dumps(planning_status_to_dict(status), ensure_ascii=False, indent=2))
    else:
        click.echo(format_planning_status_markdown(status), nl=False)


@cli.group("project")
def project_group() -> None:
    """Manage projects."""


@project_group.command("list")
@click.option("--active", is_flag=True, help="Show only active projects.")
@click.option("--sort", "sort_by", default="title",
              type=click.Choice(("title", "created", "state"), case_sensitive=False),
              help="Sort projects (default: title).")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--count", "count_only", is_flag=True, help="Show only the count.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def project_list_cmd(ctx: click.Context, active: bool, sort_by: str, compact: bool, count_only: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    projects_path = root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        if count_only:
            click.echo("0 projects")
        elif json_output:
            click.echo("[]")
        else:
            click.echo("No projects.")
        return
    from trailmind.log import read_entity_user_facing

    projects = []
    for project_path in sorted(p for p in projects_path.iterdir() if (p / "PROJECT.md").is_file()):
        try:
            fm, _body = read_entity_user_facing(project_path / "PROJECT.md", label="project")
            state = str(fm.get("state") or "unknown")
            if active and state not in ("active",):
                continue
            projects.append({
                "slug": str(fm.get("slug") or project_path.name),
                "title": str(fm.get("title") or project_path.name),
                "goal": str(fm.get("goal") or ""),
                "state": state,
                "created": str(fm.get("created") or ""),
                "path": project_path.relative_to(root).as_posix(),
            })
        except TrailmindError:
            continue
    # Sort
    STATE_ORDER = {"active": 0, "paused": 1, "completed": 2, "archived": 3}
    if sort_by == "created":
        projects.sort(key=lambda p: p.get("created", "") or "9999-99-99")
    elif sort_by == "state":
        projects.sort(key=lambda p: (STATE_ORDER.get(p.get("state", ""), 99), p.get("title", "").lower()))
    else:
        projects.sort(key=lambda p: p.get("title", "").lower())
    if count_only:
        click.echo(f"{len(projects)} project{'s' if len(projects) != 1 else ''}")
        return
    if json_output:
        click.echo(json.dumps(projects, ensure_ascii=False, indent=2))
    else:
        if not projects:
            click.echo("No projects.")
            return
        for p in projects:
            if compact:
                click.echo(f"{p['slug']:20s} {p['state']:12s} {p['title']}")
            else:
                click.echo(f"{p['slug']:20s} {p['state']:12s} {p['title']}")
                click.echo(f"{'':20s} {'':12s} {p['path']}")


@project_group.command("init")
@click.option("--slug", required=True)
@click.option("--title", required=True)
@click.option("--goal", required=True)
@click.option("--owners", default="")
@click.option("--tags", default="")
@click.pass_context
def project_init(ctx: click.Context, slug: str, title: str, goal: str, owners: str, tags: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = init_project(root, slug=slug, title=title, goal=goal, owners=_csv(owners), tags=_csv(tags))
    _echo_touched(root, touched)


@project_group.command("set-status")
@click.argument("project_slug")
@click.argument("state", type=click.Choice(PROJECT_STATES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def project_set_status(
    ctx: click.Context,
    project_slug: str,
    state: str,
    actor: str,
    note: str | None,
) -> None:
    """Change a project's state."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_project_status(root, project_slug=project_slug, state=state, actor=actor, note=note)
    _echo_touched(root, [touched])


@project_group.command("edit")
@click.argument("project_slug")
@click.option("--title", default=None, help="New project title.")
@click.option("--goal", default=None, help="New project goal.")
@click.option("--owners", default=None, help="Comma-separated owner emails/shortnames.")
@click.option("--tags", default=None, help="Comma-separated tags.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def project_edit(
    ctx: click.Context,
    project_slug: str,
    title: str | None,
    goal: str | None,
    owners: str | None,
    tags: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on a project."""
    root = find_repo_root(_cwd_from_context(ctx))
    owner_list = split_csv(owners) if owners is not None else None
    tag_list = split_csv(tags) if tags is not None else None
    touched = edit_project(
        root,
        project_slug=project_slug,
        actor=actor,
        title=title,
        goal=goal,
        owners=owner_list,
        tags=tag_list,
        note=note,
    )
    _echo_touched(root, [touched])


@project_group.command("show")
@click.argument("project_slug")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def project_show(ctx: click.Context, project_slug: str, json_output: bool) -> None:
    """Show details of a single project."""
    root = find_repo_root(_cwd_from_context(ctx))
    from trailmind.log import read_entity_user_facing
    from trailmind.errors import TrailmindError

    # Resolve project directory
    proj_dir = root / "projects" / project_slug
    proj_md = proj_dir / "PROJECT.md"
    if not proj_md.exists():
        # Try as full path
        proj_dir = root / project_slug
        proj_md = proj_dir / "PROJECT.md"
    if not proj_md.exists():
        raise TrailmindError(f"project not found: {project_slug}")

    frontmatter, body = read_entity_user_facing(proj_md, label="project")
    data = {
        "path": str(proj_md.relative_to(root)),
        "body": body.strip(),
    }
    for key, value in frontmatter.items():
        if value is not None:
            data[key] = value

    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Project"), nl=False)


@cli.group("epic")
def epic_group() -> None:
    """Manage epics."""


@epic_group.command("list")
@click.option("--project", "project_slug", default=None)
@click.option("--active", is_flag=True, help="Show only active epics.")
@click.option("--sort", "sort_by", default="title",
              type=click.Choice(("title", "created", "state"), case_sensitive=False),
              help="Sort epics (default: title).")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--count", "count_only", is_flag=True, help="Show only the count.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def epic_list_cmd(ctx: click.Context, project_slug: str | None, active: bool,
                   sort_by: str, compact: bool, count_only: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    from trailmind.log import read_entity_user_facing

    epics = []
    projects_path = root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        if count_only:
            click.echo("0 epics")
        elif json_output:
            click.echo("[]")
        else:
            click.echo("No epics.")
        return

    project_dirs = []
    if project_slug:
        candidate = projects_path / project_slug
        if (candidate / "PROJECT.md").is_file():
            project_dirs = [candidate]
    else:
        project_dirs = sorted(p for p in projects_path.iterdir() if (p / "PROJECT.md").is_file())

    for project_dir in project_dirs:
        for epic_dir in sorted(e for e in project_dir.iterdir() if (e / "EPIC.md").is_file()):
            try:
                fm, _body = read_entity_user_facing(epic_dir / "EPIC.md", label="epic")
                state = str(fm.get("state") or "unknown")
                if active and state not in ("active",):
                    continue
                epics.append({
                    "project": project_dir.name,
                    "slug": str(fm.get("slug") or epic_dir.name),
                    "title": str(fm.get("title") or epic_dir.name),
                    "goal": str(fm.get("goal") or ""),
                    "state": state,
                    "target": str(fm.get("target") or ""),
                    "created": str(fm.get("created") or ""),
                    "path": epic_dir.relative_to(root).as_posix(),
                })
            except TrailmindError:
                continue
    # Sort
    EPIC_STATE_ORDER = {"active": 0, "paused": 1, "completed": 2, "archived": 3}
    if sort_by == "created":
        epics.sort(key=lambda e: e.get("created", "") or "9999-99-99")
    elif sort_by == "state":
        epics.sort(key=lambda e: (EPIC_STATE_ORDER.get(e.get("state", ""), 99), e.get("title", "").lower()))
    else:
        epics.sort(key=lambda e: e.get("title", "").lower())
    if count_only:
        click.echo(f"{len(epics)} epic{'s' if len(epics) != 1 else ''}")
        return
    if json_output:
        click.echo(json.dumps(epics, ensure_ascii=False, indent=2))
    else:
        if not epics:
            click.echo("No epics.")
            return
        for e in epics:
            if compact:
                click.echo(f"{e['project'] + '/' + e['slug']:30s} {e['state']:12s} {e['title']}")
            else:
                click.echo(f"{e['project'] + '/' + e['slug']:30s} {e['state']:12s} {e['title']}")
                click.echo(f"{'':30s} {'':12s} {e['path']}")


@epic_group.command("init")
@click.option("--project", required=True)
@click.option("--slug", required=True)
@click.option("--title", required=True)
@click.option("--goal", required=True)
@click.option("--start", default="")
@click.option("--target", default="")
@click.option("--roster", default="")
@click.option("--repos", default="")
@click.pass_context
def epic_init(
    ctx: click.Context,
    project: str,
    slug: str,
    title: str,
    goal: str,
    start: str,
    target: str,
    roster: str,
    repos: str,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = init_epic(
        root,
        project=project,
        slug=slug,
        title=title,
        goal=goal,
        start=start,
        target=target,
        roster=_csv(roster),
        repos=_csv(repos),
    )
    _echo_touched(root, touched)


@epic_group.command("set-status")
@click.argument("epic_ref")
@click.argument("state", type=click.Choice(EPIC_STATES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def epic_set_status(
    ctx: click.Context,
    epic_ref: str,
    state: str,
    actor: str,
    note: str | None,
) -> None:
    """Change an epic's state."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_epic_status(root, epic_ref=epic_ref, state=state, actor=actor, note=note)
    _echo_touched(root, [touched])


@epic_group.command("edit")
@click.argument("epic_ref")
@click.option("--title", default=None, help="New epic title.")
@click.option("--goal", default=None, help="New epic goal.")
@click.option("--target", default=None, help="New target date (YYYY-MM-DD).")
@click.option("--roster", default=None, help="Comma-separated roster shortnames.")
@click.option("--repos", default=None, help="Comma-separated repo names.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def epic_edit(
    ctx: click.Context,
    epic_ref: str,
    title: str | None,
    goal: str | None,
    target: str | None,
    roster: str | None,
    repos: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on an epic."""
    root = find_repo_root(_cwd_from_context(ctx))
    roster_list = split_csv(roster) if roster is not None else None
    repo_list = split_csv(repos) if repos is not None else None
    touched = edit_epic(
        root,
        epic_ref=epic_ref,
        actor=actor,
        title=title,
        goal=goal,
        target=target,
        roster=roster_list,
        repos=repo_list,
        note=note,
    )
    _echo_touched(root, [touched])


@epic_group.command("show")
@click.argument("epic_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def epic_show(ctx: click.Context, epic_ref: str, json_output: bool) -> None:
    """Show details of a single epic."""
    root = find_repo_root(_cwd_from_context(ctx))
    from trailmind.log import read_entity_user_facing
    from trailmind.errors import TrailmindError
    from trailmind.scopes import resolve_epic_dir

    epic_path = resolve_epic_dir(root, epic_ref)
    epic_md = epic_path / "EPIC.md"
    if not epic_md.exists():
        raise TrailmindError(f"epic not found: {epic_ref}")

    frontmatter, body = read_entity_user_facing(epic_md, label="epic")
    data = {
        "path": str(epic_md.relative_to(root)),
        "body": body.strip(),
    }
    for key, value in frontmatter.items():
        if value is not None:
            data[key] = value

    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Epic"), nl=False)


@cli.group("task")
def task_group() -> None:
    """Manage tasks."""


@task_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, type=click.Choice(TASK_STATUSES, case_sensitive=False),
              help="Filter by task status.")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--priority", default=None, type=click.Choice(TASK_PRIORITIES, case_sensitive=False),
              help="Filter by priority.")
@click.option("--due-before", default=None, help="Filter tasks due before YYYY-MM-DD.")
@click.option("--due-after", default=None, help="Filter tasks due after YYYY-MM-DD.")
@click.option("--overdue", is_flag=True, help="Show only overdue tasks (not done/wontfix).")
@click.option("--due-within", "due_within_days", default=None, type=click.IntRange(min=1),
              help="Show tasks due within N days (not done/wontfix, not overdue).")
@click.option("--due-today", is_flag=True, help="Show tasks due today (shortcut for --due-within 0).")
@click.option("--created-since", default=None, help="Filter tasks created on or after YYYY-MM-DD.")
@click.option("--created-before", default=None, help="Filter tasks created before YYYY-MM-DD.")
@click.option("--active", is_flag=True, help="Show only active tasks (not done or wontfix).")
@click.option("--blocked", is_flag=True, help="Show only blocked tasks.")
@click.option("--ready-only", is_flag=True, help="Show only ready tasks (ready to start).")
@click.option("--in-progress", "in_progress_only", is_flag=True, help="Show only in-progress tasks.")
@click.option("--has-due", "has_due", flag_value=True, default=None,
              help="Show only tasks that have a due date.")
@click.option("--no-due", "has_due", flag_value=False,
              help="Show only tasks without a due date.")
@click.option("--tag", default=None, help="Filter by tag (case-insensitive substring match).")
@click.option("--no-tags", is_flag=True, help="Show only tasks without any tags.")
@click.option("--has-deliverables", is_flag=True, help="Show only tasks that have deliverables defined.")
@click.option("--no-deliverables", is_flag=True, help="Show only tasks without deliverables.")
@click.option("--has-known-issues", is_flag=True, help="Show only tasks that have known issues.")
@click.option("--no-known-issues", is_flag=True, help="Show only tasks without known issues.")
@click.option("--has-deps", is_flag=True, help="Show only tasks that have dependencies.")
@click.option("--no-deps", is_flag=True, help="Show only tasks without dependencies.")
@click.option("--unassigned", is_flag=True, help="Show only tasks without an owner.")
@click.option("--stale-days", default=None, type=click.IntRange(min=1),
              help="Show only tasks with no activity in N days (approximated by created date for done tasks).")
@click.option("--title-contains", default=None, help="Filter by title substring (case-insensitive).")
@click.option("--created-today", is_flag=True, help="Show only tasks created today.")
@click.option("--created-this-week", is_flag=True, help="Show only tasks created this week.")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "priority", "due", "status", "title"), case_sensitive=False),
              help="Sort tasks (default: created).")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "owner", "priority", "epic", "project", "tag", "due"), case_sensitive=False),
              help="Group tasks by status, owner, priority, epic, project, tag, or due date.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--ids", "ids_only", is_flag=True, help="Output only entity IDs (one per line, for piping).")
@click.option("--count", "count_only", is_flag=True, help="Show only the count of matching tasks.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV for spreadsheet import.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def task_list_cmd(
    ctx: click.Context,
    epic_ref: str | None,
    project_ref: str | None,
    status: str | None,
    owner: str | None,
    priority: str | None,
    due_before: str | None,
    due_after: str | None,
    overdue: bool,
    due_within_days: int | None,
    due_today: bool,
    created_since: str | None,
    created_before: str | None,
    active: bool,
    blocked: bool,
    ready_only: bool,
    in_progress_only: bool,
    has_due: bool | None,
    tag: str | None,
    no_tags: bool,
    has_deliverables: bool,
    no_deliverables: bool,
    has_known_issues: bool,
    no_known_issues: bool,
    has_deps: bool,
    no_deps: bool,
    unassigned: bool,
    stale_days: int | None,
    title_contains: str | None,
    created_today: bool,
    created_this_week: bool,
    sort_by: str,
    group_by: str | None,
    compact: bool,
    ids_only: bool,
    count_only: bool,
    csv_output: bool,
    limit: int | None,
    json_output: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))

    # --due-today is a shortcut for --due-within 0
    effective_due_within = due_within_days
    if due_today:
        effective_due_within = 0

    tasks = list_tasks(
        root,
        epic_ref=epic_ref,
        project_ref=project_ref,
        status=status,
        owner=owner,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        due_within_days=effective_due_within,
        has_due=has_due,
        tag=tag,
        sort_by=sort_by,
    )
    if active:
        tasks = [t for t in tasks if t.get("status") not in ("done", "wontfix")]
    if blocked:
        tasks = [t for t in tasks if t.get("status") == "blocked"]
    if ready_only:
        tasks = [t for t in tasks if t.get("status") in ("ready", "created")]
    if in_progress_only:
        tasks = [t for t in tasks if t.get("status") == "in_progress"]
    if has_deliverables:
        tasks = [t for t in tasks if t.get("deliverables")]
    if no_deliverables:
        tasks = [t for t in tasks if not t.get("deliverables")]
    if has_known_issues:
        tasks = [t for t in tasks if t.get("known_issues")]
    if no_known_issues:
        tasks = [t for t in tasks if not t.get("known_issues")]
    if has_deps:
        tasks = [t for t in tasks if t.get("depends_on") or t.get("soft_depends_on")]
    if no_deps:
        tasks = [t for t in tasks if not t.get("depends_on") and not t.get("soft_depends_on")]
    if no_tags:
        tasks = [t for t in tasks if not t.get("tags")]
    if unassigned:
        tasks = [t for t in tasks if not t.get("owner")]
    if title_contains:
        needle = title_contains.lower()
        tasks = [t for t in tasks if needle in (t.get("title") or "").lower()]
    # --stale-days: tasks with no recent activity (approximate using created date for non-done tasks)
    if stale_days is not None:
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=stale_days)).isoformat()
        tasks = [t for t in tasks if t.get("created") and t["created"] <= cutoff
                 and t.get("status") not in ("done", "wontfix")]
    # --created-today and --created-this-week are shortcuts
    if created_today or created_this_week:
        from datetime import date, timedelta
        today = date.today()
        if created_today:
            today_str = today.isoformat()
            tasks = [t for t in tasks if t.get("created") == today_str]
        elif created_this_week:
            week_start = today - timedelta(days=today.weekday())
            week_start_str = week_start.isoformat()
            tasks = [t for t in tasks if t.get("created") and t["created"] >= week_start_str]
    if created_since:
        tasks = [t for t in tasks if t.get("created") and t["created"] >= created_since]
    if created_before:
        tasks = [t for t in tasks if t.get("created") and t["created"] < created_before]
    if ids_only:
        for t in tasks:
            click.echo(t.get("id", ""))
        return
    if count_only:
        click.echo(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")
        return
    if limit:
        tasks = tasks[:limit]
    if csv_output:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "title", "status", "priority", "owner", "due", "tags", "created", "path"])
        for t in tasks:
            writer.writerow([
                t.get("id", ""), t.get("title", ""), t.get("status", ""),
                t.get("priority", ""), t.get("owner", ""), t.get("due", ""),
                ";".join(t.get("tags", [])),
                t.get("created", ""), t.get("path", ""),
            ])
        click.echo(output.getvalue(), nl=False)
        return

    if json_output:
        click.echo(json.dumps(tasks, ensure_ascii=False, indent=2))
        return

    if not tasks:
        click.echo("No tasks.")
        return

    if group_by:
        from collections import defaultdict
        from datetime import date, timedelta
        groups: dict[str, list[dict]] = defaultdict(list)
        today = date.today()
        for t in tasks:
            if group_by == "epic":
                key = t.get("epic", "") or "unknown"
                groups[key].append(t)
            elif group_by == "project":
                epic_path = t.get("epic", "") or ""
                parts = epic_path.split("/")
                key = parts[1] if len(parts) > 1 else "unknown"
                groups[key].append(t)
            elif group_by == "tag":
                tags = t.get("tags") or []
                if tags:
                    for tag in tags:
                        groups[str(tag)].append(t)
                else:
                    groups["untagged"].append(t)
            elif group_by == "due":
                due_str = t.get("due", "")
                status = t.get("status", "")
                if not due_str:
                    groups["📅 No due date"].append(t)
                elif status in ("done", "wontfix"):
                    groups["✅ Done"].append(t)
                else:
                    try:
                        due_date = date.fromisoformat(due_str)
                        delta = (due_date - today).days
                        if delta < 0:
                            groups["⚠️ Overdue"].append(t)
                        elif delta == 0:
                            groups["📍 Today"].append(t)
                        elif delta <= 7:
                            groups["📆 This week"].append(t)
                        elif delta <= 14:
                            groups["📆 Next week"].append(t)
                        elif delta <= 30:
                            groups["🗓️ This month"].append(t)
                        else:
                            groups["🔮 Later"].append(t)
                    except ValueError:
                        groups["📅 No due date"].append(t)
            else:
                key = t.get(group_by, "") or "unassigned"
                groups[key].append(t)

        # Sort groups: by natural order for status/priority, custom for due, alphabetical for rest
        if group_by == "status":
            order = {s: i for i, s in enumerate(TASK_STATUSES)}
            sorted_keys = sorted(groups.keys(), key=lambda k: order.get(k, 99))
        elif group_by == "priority":
            from trailmind.task import PRIORITY_ORDER
            sorted_keys = sorted(groups.keys(), key=lambda k: PRIORITY_ORDER.get(k, 99))
        elif group_by == "due":
            # Custom order for due buckets
            due_order = ["⚠️ Overdue", "📍 Today", "📆 This week", "📆 Next week",
                         "🗓️ This month", "🔮 Later", "✅ Done", "📅 No due date"]
            due_rank = {k: i for i, k in enumerate(due_order)}
            sorted_keys = sorted(groups.keys(), key=lambda k: due_rank.get(k, 99))
        else:
            sorted_keys = sorted(groups.keys())

        for key in sorted_keys:
            group_tasks = groups[key]
            display_key = key
            if group_by == "epic":
                # Show just the epic slug (last part of path)
                display_key = key.split("/")[-1] if "/" in key else key
            click.echo(f"\n{display_key.upper()} ({len(group_tasks)})")
            click.echo("─" * 60)
            for t in group_tasks:
                due = t.get("due", "")
                pri = t.get("priority", "")
                tags = t.get("tags") or []
                tag_str = f" ({', '.join(tags)})" if tags else ""
                extras = f" [{pri}]" if pri else ""
                due_str = f" due:{due}" if due else ""
                if compact:
                    click.echo(f"  {t['id']:16s} {t['status']:12s} {t['owner']:10s}{extras}{due_str}{tag_str}  {t['title']}")
                else:
                    click.echo(f"  {t['id']:16s} {t['status']:14s} {t['owner']:12s}{extras}{due_str}{tag_str}  {t['title']}")
                    click.echo(f"  {'':16s} {'':14s} {'':12s}  {t['path']}")
    else:
        for t in tasks:
            due = t.get("due", "")
            pri = t.get("priority", "")
            tags = t.get("tags") or []
            tag_str = f" ({', '.join(tags)})" if tags else ""
            extras = f" [{pri}]" if pri else ""
            due_str = f" due:{due}" if due else ""
            if compact:
                click.echo(f"{t['id']:16s} {t['status']:12s} {t['owner']:10s}{extras}{due_str}{tag_str}  {t['title']}")
            else:
                click.echo(f"{t['id']:16s} {t['status']:14s} {t['owner']:12s}{extras}{due_str}{tag_str}  {t['title']}")
                click.echo(f"{'':16s} {'':14s} {'':12s}  {t['path']}")


@task_group.command("add")
@click.option("--epic", required=True)
@click.option("--filer", required=True)
@click.option("--owner", required=True)
@click.option("--title", required=True)
@click.option("--code-paths", default="")
@click.option("--design-doc", default=None)
@click.option("--depends-on", default="")
@click.option("--soft-depends-on", default="")
@click.option("--known-issues", default="")
@click.option("--deliverables", default="")
@click.option("--priority", default=DEFAULT_PRIORITY, show_default=True,
              type=click.Choice(TASK_PRIORITIES, case_sensitive=False),
              help="Task priority level.")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD).")
@click.option("--tags", default=None, help="Comma-separated tags.")
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def task_add(
    ctx: click.Context,
    epic: str,
    filer: str,
    owner: str,
    title: str,
    code_paths: str,
    design_doc: str | None,
    depends_on: str,
    soft_depends_on: str,
    known_issues: str,
    deliverables: str,
    priority: str,
    due: str | None,
    tags: str | None,
    dry_run: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    tag_list = split_csv(tags) if tags else []
    if dry_run:
        click.echo(f"[DRY RUN] Would create task in {epic}:")
        click.echo(f"  Title: {title}")
        click.echo(f"  Filer: {filer}, Owner: {owner}")
        click.echo(f"  Priority: {priority}, Due: {due or '(none)'}")
        if tag_list:
            click.echo(f"  Tags: {', '.join(tag_list)}")
        return
    touched = add_task(
        root,
        epic=epic,
        filer=filer,
        owner=owner,
        title=title,
        code_paths=split_csv(code_paths),
        design_doc=design_doc,
        depends_on=split_csv(depends_on),
        soft_depends_on=split_csv(soft_depends_on),
        known_issues=split_csv(known_issues),
        deliverables=split_csv(deliverables),
        priority=priority,
        due=due,
        tags=tag_list,
    )
    _echo_touched(root, [touched])


@task_group.command("bulk-add")
@click.option("--epic", required=True)
@click.option("--filer", required=True)
@click.option("--input-file", "input_file", required=True,
              help="CSV or JSON file with tasks (columns: title, owner, priority, due, tags).")
@click.option("--format", "fmt", default="csv", type=click.Choice(("csv", "json"), case_sensitive=False),
              help="Input file format (default: csv).")
@click.option("--default-owner", default=None, help="Default owner if not specified in file.")
@click.option("--default-priority", default=DEFAULT_PRIORITY, show_default=True,
              type=click.Choice(TASK_PRIORITIES, case_sensitive=False),
              help="Default priority if not specified in file.")
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def task_bulk_add(
    ctx: click.Context,
    epic: str,
    filer: str,
    input_file: str,
    fmt: str,
    default_owner: str | None,
    default_priority: str,
    dry_run: bool,
) -> None:
    """Bulk-add tasks from a CSV or JSON file."""
    import csv
    import json as _json
    root = find_repo_root(_cwd_from_context(ctx))

    # Read input file
    path = Path(input_file)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise TrailmindError(f"input file not found: {input_file}")

    content = path.read_text(encoding="utf-8")

    # Parse
    task_specs: list[dict] = []
    if fmt == "json":
        data = _json.loads(content)
        if isinstance(data, list):
            task_specs = data
        elif isinstance(data, dict) and "tasks" in data:
            task_specs = data["tasks"]
        else:
            raise TrailmindError("JSON must be a list or object with 'tasks' key.")
    else:  # csv
        reader = csv.DictReader(content.splitlines())
        for row in reader:
            task_specs.append(dict(row))

    if not task_specs:
        raise TrailmindError("no tasks found in input file")

    if dry_run:
        click.echo(f"[DRY RUN] Would create {len(task_specs)} task(s) in {epic}:")
        for i, spec in enumerate(task_specs):
            title = spec.get("title", "(untitled)")
            owner = spec.get("owner") or default_owner or "(unassigned)"
            click.echo(f"  {i+1}. {title} (owner: @{owner})")
        return

    touched = []
    for i, spec in enumerate(task_specs):
        title = spec.get("title", "").strip()
        if not title:
            click.echo(f"  ⚠ task {i+1}: missing title, skipping", err=True)
            continue
        owner = spec.get("owner") or default_owner
        if not owner:
            click.echo(f"  ⚠ task {i+1} ({title}): missing owner, skipping", err=True)
            continue
        priority = spec.get("priority") or default_priority
        due = spec.get("due") or None
        tags_str = spec.get("tags") or ""
        tag_list = split_csv(tags_str) if tags_str else []
        code_paths_str = spec.get("code_paths") or ""
        depends_on_str = spec.get("depends_on") or ""
        known_issues_str = spec.get("known_issues") or ""
        deliverables_str = spec.get("deliverables") or ""

        try:
            path = add_task(
                root,
                epic=epic,
                filer=filer,
                owner=owner,
                title=title,
                code_paths=split_csv(code_paths_str),
                depends_on=split_csv(depends_on_str),
                known_issues=split_csv(known_issues_str),
                deliverables=split_csv(deliverables_str),
                priority=priority,
                due=due,
                tags=tag_list,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {title}: {exc}", err=True)

    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nCreated {len(touched)}/{len(task_specs)} tasks.")


@task_group.command("update")
@click.argument("task_ref")
@click.option("--status", required=True)
@click.pass_context
def task_update(ctx: click.Context, task_ref: str, status: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = update_task_status(root, task_ref=task_ref, status=status)
    _echo_touched(root, [touched])


@task_group.command("set-status")
@click.argument("task_ref")
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_set_status(
    ctx: click.Context,
    task_ref: str,
    status: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would set {task_ref} status to {status!r}")
        return
    touched, warning = set_task_status(root, task_ref=task_ref, status=status, actor=actor, note=note)
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("set-priority")
@click.argument("task_ref")
@click.argument("priority", type=click.Choice(TASK_PRIORITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_set_priority(
    ctx: click.Context,
    task_ref: str,
    priority: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would set {task_ref} priority to {priority!r}")
        return
    touched = set_task_priority(root, task_ref=task_ref, priority=priority, actor=actor, note=note)
    _echo_touched(root, [touched])


@task_group.command("bulk-priority")
@click.argument("task_refs", nargs=-1)
@click.argument("priority", type=click.Choice(TASK_PRIORITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_bulk_priority(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    priority: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-set priority for tasks (e.g. T-001 T-002 high, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set priority to {priority!r} for {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = set_task_priority(root, task_ref=task_ref, priority=priority, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("due")
@click.argument("task_ref")
@click.argument("due_date", required=False, default=None)
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--clear", is_flag=True, help="Clear the due date.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_due(
    ctx: click.Context,
    task_ref: str,
    due_date: str | None,
    actor: str,
    note: str | None,
    clear: bool,
    dry_run: bool,
) -> None:
    """Set or clear a task due date (YYYY-MM-DD)."""
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        action = "clear" if clear else f"set to {due_date!r}"
        click.echo(f"[DRY RUN] Would {action} due date for {task_ref}")
        return
    if clear:
        touched = set_task_due(root, task_ref=task_ref, due_date=None, actor=actor, note=note)
    else:
        if due_date is None:
            raise TrailmindError("due date is required (or use --clear)")
        touched = set_task_due(root, task_ref=task_ref, due_date=due_date, actor=actor, note=note)
    _echo_touched(root, [touched])


@task_group.command("bulk-due-set")
@click.argument("task_refs", nargs=-1)
@click.argument("due_date")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_bulk_due_set(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    due_date: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-set due date for tasks (e.g. T-001 T-002 2026-08-01, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set due date to {due_date!r} for {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = set_task_due(root, task_ref=task_ref, due_date=due_date, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("bulk-due-clear")
@click.argument("task_refs", nargs=-1)
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_bulk_due_clear(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-clear due date for tasks (e.g. T-001 T-002, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would clear due date for {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = set_task_due(root, task_ref=task_ref, due_date=None, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("assign")
@click.argument("task_ref")
@click.argument("owner")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_assign(
    ctx: click.Context,
    task_ref: str,
    owner: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Reassign a task to a different owner."""
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would assign {task_ref} to @{owner}")
        return
    touched = assign_task(root, task_ref=task_ref, owner=owner, actor=actor, note=note)
    _echo_touched(root, [touched])


@task_group.group("tag")
def task_tag_group() -> None:
    """Manage task tags."""


@task_tag_group.command("add")
@click.argument("task_ref")
@click.argument("tag")
@click.option("--actor", required=True)
@click.pass_context
def task_tag_add(ctx: click.Context, task_ref: str, tag: str, actor: str) -> None:
    """Add a tag to a task."""
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    from trailmind.entity_io import write_entity

    root = find_repo_root(_cwd_from_context(ctx))
    path = resolve_entity(root, raw=task_ref, entity="T")
    fm, body = read_entity_user_facing(path, label="task")
    tags = list(fm.get("tags") or [])
    if tag not in tags:
        tags.append(tag)
        fm["tags"] = tags
        write_entity(path, frontmatter=fm, body=body)
        _echo_touched(root, [path])
    else:
        click.echo(f"Tag {tag!r} already on task.")


@task_tag_group.command("remove")
@click.argument("task_ref")
@click.argument("tag")
@click.option("--actor", required=True)
@click.pass_context
def task_tag_remove(ctx: click.Context, task_ref: str, tag: str, actor: str) -> None:
    """Remove a tag from a task."""
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    from trailmind.entity_io import write_entity

    root = find_repo_root(_cwd_from_context(ctx))
    path = resolve_entity(root, raw=task_ref, entity="T")
    fm, body = read_entity_user_facing(path, label="task")
    tags = list(fm.get("tags") or [])
    if tag in tags:
        tags.remove(tag)
        fm["tags"] = tags
        write_entity(path, frontmatter=fm, body=body)
        _echo_touched(root, [path])
    else:
        click.echo(f"Tag {tag!r} not found on task.")


@task_tag_group.command("bulk-add")
@click.argument("task_refs", nargs=-1)
@click.argument("tag")
@click.option("--actor", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_tag_bulk_add(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    tag: str,
    actor: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-add a tag to multiple tasks."""
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    from trailmind.entity_io import write_entity

    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would add tag {tag!r} to {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = resolve_entity(root, raw=task_ref, entity="T")
            fm, body = read_entity_user_facing(path, label="task")
            tags = list(fm.get("tags") or [])
            if tag not in tags:
                tags.append(tag)
                fm["tags"] = tags
                write_entity(path, frontmatter=fm, body=body)
                touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nAdded tag {tag!r} to {len(touched)} task(s).")


@task_tag_group.command("bulk-remove")
@click.argument("task_refs", nargs=-1)
@click.argument("tag")
@click.option("--actor", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_tag_bulk_remove(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    tag: str,
    actor: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-remove a tag from multiple tasks."""
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    from trailmind.entity_io import write_entity

    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would remove tag {tag!r} from {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = resolve_entity(root, raw=task_ref, entity="T")
            fm, body = read_entity_user_facing(path, label="task")
            tags = list(fm.get("tags") or [])
            if tag in tags:
                tags.remove(tag)
                fm["tags"] = tags
                write_entity(path, frontmatter=fm, body=body)
                touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nRemoved tag {tag!r} from {len(touched)} task(s).")


@task_group.command("show")
@click.argument("task_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def task_show(ctx: click.Context, task_ref: str, json_output: bool) -> None:
    """Show details of a single task."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = show_entity(root, task_ref, "T")
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Task"), nl=False)


@task_group.command("comment")
@click.argument("task_ref")
@click.option("--author", required=True, help="Author email or shortname.")
@click.option("--text", required=True, help="Comment text.")
@click.pass_context
def task_comment(ctx: click.Context, task_ref: str, author: str, text: str) -> None:
    """Add a dated, attributed comment to a task."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = comment_task(root, task_ref=task_ref, author=author, text=text)
    _echo_touched(root, [touched])


@task_group.command("start")
@click.argument("task_ref")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_start(
    ctx: click.Context,
    task_ref: str,
    actor: str,
    note: str | None,
) -> None:
    """Mark a task as in_progress."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched, warning = start_task(root, task_ref=task_ref, actor=actor, note=note)
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("done")
@click.argument("task_ref")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_done(
    ctx: click.Context,
    task_ref: str,
    actor: str,
    note: str | None,
) -> None:
    """Mark a task as done."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched, warning = complete_task(root, task_ref=task_ref, actor=actor, note=note)
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("reopen")
@click.argument("task_ref")
@click.option("--to", "target_status", default="ready", type=click.Choice(("ready", "in_progress"), case_sensitive=False),
              help="Status to reopen to (default: ready).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_reopen(
    ctx: click.Context,
    task_ref: str,
    target_status: str,
    actor: str,
    note: str | None,
) -> None:
    """Reopen a done or wontfix task."""
    root = find_repo_root(_cwd_from_context(ctx))
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    task_path = resolve_entity(root, raw=task_ref, entity="T")
    fm, _body = read_entity_user_facing(task_path, label="task")
    current = str(fm.get("status", "created"))
    if current not in ("done", "wontfix"):
        raise click.UsageError(f"cannot reopen task with status {current!r} (must be done or wontfix)")
    touched, warning = set_task_status(root, task_ref=task_ref, status=target_status, actor=actor,
                                       note=note or "Reopened")
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("next")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--epic", "epic_ref", default=None, help="Filter by epic path.")
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--tag", default=None, help="Filter by tag (case-insensitive substring match).")
@click.option("--limit", default=10, show_default=True, type=click.IntRange(min=1, max=50),
              help="Maximum tasks to show.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def task_next(ctx: click.Context, owner: str | None, epic_ref: str | None, project_ref: str | None,
              tag: str | None, limit: int, json_output: bool) -> None:
    """Show the most actionable tasks next to work on (sorted by priority then due date)."""
    root = find_repo_root(_cwd_from_context(ctx))
    tasks = next_tasks(root, owner=owner, epic=epic_ref, project=project_ref, tag=tag, limit=limit)

    if json_output:
        # Remove internal sort keys
        clean = [{k: v for k, v in t.items() if not k.startswith("_")} for t in tasks]
        click.echo(json.dumps(clean, ensure_ascii=False, indent=2))
        return

    if not tasks:
        click.echo("No actionable tasks found. All caught up! 🎉")
        return

    click.echo("Next tasks to work on:\n")
    for i, t in enumerate(tasks, 1):
        pri = t.get("priority", "")
        pri_str = f" [{pri.upper()}]" if pri else ""
        due = t.get("due", "")
        due_str = f" due:{due}" if due else ""
        status = t.get("status", "")
        in_prog = " (in progress)" if t.get("_in_progress") else ""
        owner_str = f" @{t.get('owner', '')}" if t.get("owner") else ""
        click.echo(f"  {i:2d}. {t['id']}{pri_str}{owner_str}{due_str}{in_prog}")
        click.echo(f"      {t['title']}")
        click.echo(f"      {t['path']}")
        if i < len(tasks):
            click.echo()


@task_group.command("start-next")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--epic", "epic_ref", default=None, help="Filter by epic path.")
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_start_next(ctx: click.Context, owner: str | None, epic_ref: str | None,
                     project_ref: str | None, actor: str, note: str | None,
                     dry_run: bool) -> None:
    """Automatically start the next most actionable task."""
    root = find_repo_root(_cwd_from_context(ctx))
    tasks = next_tasks(root, owner=owner, epic=epic_ref, project=project_ref, limit=1)

    if not tasks:
        click.echo("No actionable tasks found. All caught up! 🎉")
        return

    next_task = tasks[0]
    task_ref = next_task.get("id", "")

    if dry_run:
        click.echo(f"[DRY RUN] Would start {task_ref}: {next_task.get('title', '')}")
        return

    touched, warning = start_task(root, task_ref=task_ref, actor=actor, note=note)
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("edit")
@click.argument("task_ref")
@click.option("--title", default=None, help="New task title.")
@click.option("--code-paths", default=None, help="Comma-separated code paths.")
@click.option("--design-doc", default=None, help="Path to design document.")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD), or empty string to clear.")
@click.option("--tags", default=None, help="Comma-separated tags (replaces existing).")
@click.option("--known-issues", default=None, help="Comma-separated known issue IDs (replaces existing).")
@click.option("--deliverables", default=None, help="Comma-separated deliverables (replaces existing).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_edit(
    ctx: click.Context,
    task_ref: str,
    title: str | None,
    code_paths: str | None,
    design_doc: str | None,
    due: str | None,
    tags: str | None,
    known_issues: str | None,
    deliverables: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on a task."""
    root = find_repo_root(_cwd_from_context(ctx))
    paths = split_csv(code_paths) if code_paths is not None else None
    tag_list = split_csv(tags) if tags is not None else None
    ki_list = split_csv(known_issues) if known_issues is not None else None
    del_list = split_csv(deliverables) if deliverables is not None else None
    touched = edit_task(
        root,
        task_ref=task_ref,
        actor=actor,
        title=title,
        code_paths=paths,
        design_doc=design_doc,
        due=due,
        tags=tag_list,
        known_issues=ki_list,
        deliverables=del_list,
        note=note,
    )
    _echo_touched(root, [touched])


@task_group.command("bulk-edit")
@click.option("--input-file", "input_file", required=True,
              help="CSV or JSON file with task edits (must have 'id' column; optional: title, due, tags, known_issues, deliverables, code_paths).")
@click.option("--format", "fmt", default="csv", type=click.Choice(("csv", "json"), case_sensitive=False),
              help="Input file format (default: csv).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_bulk_edit(
    ctx: click.Context,
    input_file: str,
    fmt: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Bulk-edit tasks from a CSV or JSON file (identified by 'id' column)."""
    import csv
    import json as _json
    root = find_repo_root(_cwd_from_context(ctx))

    path = Path(input_file)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise TrailmindError(f"input file not found: {input_file}")

    content = path.read_text(encoding="utf-8")

    edit_specs: list[dict] = []
    if fmt == "json":
        data = _json.loads(content)
        if isinstance(data, list):
            edit_specs = data
        elif isinstance(data, dict) and "tasks" in data:
            edit_specs = data["tasks"]
        else:
            raise TrailmindError("JSON must be a list or object with 'tasks' key.")
    else:
        reader = csv.DictReader(content.splitlines())
        for row in reader:
            edit_specs.append(dict(row))

    if not edit_specs:
        raise TrailmindError("no task edits found in input file")

    if dry_run:
        click.echo(f"[DRY RUN] Would edit {len(edit_specs)} task(s):")
        for i, spec in enumerate(edit_specs):
            task_id = spec.get("id", "(no id)")
            changes = []
            for key in ("title", "due", "tags", "known_issues", "deliverables", "code_paths"):
                if key in spec and spec[key]:
                    changes.append(f"{key}={spec[key]}")
            click.echo(f"  {i+1}. {task_id}: {', '.join(changes) if changes else '(no changes)'}")
        return

    touched = []
    for i, spec in enumerate(edit_specs):
        task_id = spec.get("id", "").strip()
        if not task_id:
            click.echo(f"  ⚠ edit {i+1}: missing id, skipping", err=True)
            continue

        title = spec.get("title") or None
        due = spec.get("due") or None
        tags_str = spec.get("tags")
        tags = split_csv(tags_str) if tags_str is not None else None
        ki_str = spec.get("known_issues")
        known_issues = split_csv(ki_str) if ki_str is not None else None
        del_str = spec.get("deliverables")
        deliverables = split_csv(del_str) if del_str is not None else None
        cp_str = spec.get("code_paths")
        code_paths = split_csv(cp_str) if cp_str is not None else None

        try:
            path = edit_task(
                root,
                task_ref=task_id,
                actor=actor,
                title=title,
                code_paths=code_paths,
                due=due,
                tags=tags,
                known_issues=known_issues,
                deliverables=deliverables,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_id}: {exc}", err=True)

    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nEdited {len(touched)}/{len(edit_specs)} tasks.")


@task_group.command("move")
@click.argument("task_ref")
@click.argument("target_epic")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_move(
    ctx: click.Context,
    task_ref: str,
    target_epic: str,
    actor: str,
    note: str | None,
) -> None:
    """Move a task to a different epic (e.g. projects/demo/new_epic)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = move_task(
        root,
        task_ref=task_ref,
        target_epic=target_epic,
        actor=actor,
        note=note,
    )
    _echo_touched(root, [touched])


@task_group.command("rename")
@click.argument("task_ref")
@click.argument("new_title")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_rename(
    ctx: click.Context,
    task_ref: str,
    new_title: str,
    actor: str,
    note: str | None,
) -> None:
    """Rename a task (updates title and filename)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = rename_task(
        root,
        task_ref=task_ref,
        new_title=new_title,
        actor=actor,
        note=note,
    )
    _echo_touched(root, [touched])


@task_group.command("clone")
@click.argument("task_ref")
@click.option("--title", default=None, help="New task title (defaults to source title).")
@click.option("--owner", default=None, help="New owner email/shortname (defaults to actor).")
@click.option("--to-epic", "target_epic", default=None, help="Target epic (defaults to source epic).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_clone(
    ctx: click.Context,
    task_ref: str,
    title: str | None,
    owner: str | None,
    target_epic: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Clone a task, preserving priority, code paths, deliverables, etc."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = clone_task(
        root,
        task_ref=task_ref,
        actor=actor,
        title=title,
        owner=owner,
        target_epic=target_epic,
        note=note,
    )
    _echo_touched(root, [touched])


@task_group.command("bulk-status")
@click.argument("task_refs", nargs=-1)
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.pass_context
def task_bulk_status(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    status: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-update task status (e.g. T-001 T-002 ready, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set status to {status!r} for {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path, _warning = set_task_status(
                root,
                task_ref=task_ref,
                status=status,
                actor=actor,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("bulk-assign")
@click.argument("task_refs", nargs=-1)
@click.argument("owner")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.pass_context
def task_bulk_assign(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    owner: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-assign tasks to an owner (e.g. T-001 T-002 alice, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would assign {len(refs)} task(s) to @{owner}:")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = assign_task(
                root,
                task_ref=task_ref,
                owner=owner,
                actor=actor,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("bulk-due")
@click.argument("task_refs", nargs=-1)
@click.argument("due")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.pass_context
def task_bulk_due(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    due: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-set due date for tasks (e.g. T-001 T-002 2026-08-01, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set due date to {due} for {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = set_task_due(
                root,
                task_ref=task_ref,
                due=due,
                actor=actor,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("link-issue")
@click.argument("task_ref")
@click.argument("issue_ref")
@click.pass_context
def task_link_issue(ctx: click.Context, task_ref: str, issue_ref: str) -> None:
    """Link a task to an issue (e.g. T-001 I-001)."""
    from trailmind.issue import link_issue_to_task
    root = find_repo_root(_cwd_from_context(ctx))
    touched = link_issue_to_task(root, task_ref=task_ref, issue_ref=issue_ref)
    _echo_touched(root, touched)


@task_group.command("unlink-issue")
@click.argument("task_ref")
@click.argument("issue_ref")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_unlink_issue(ctx: click.Context, task_ref: str, issue_ref: str,
                       actor: str, note: str | None) -> None:
    """Unlink a task from an issue (e.g. T-001 I-001)."""
    root = find_repo_root(_cwd_from_context(ctx))
    # Remove from issue's linked_tasks
    from trailmind.resolver import resolve_entity
    from trailmind.log import read_entity_user_facing
    from trailmind.entity_io import write_entity
    from trailmind.activity import append_activity_entry, action_activity_entry

    issue_path = resolve_entity(root, raw=issue_ref, entity="I")
    fm, body = read_entity_user_facing(issue_path, label="issue")
    linked = list(fm.get("linked_tasks") or [])
    if task_ref in linked:
        linked.remove(task_ref)
    fm["linked_tasks"] = linked
    action = f"Unlinked task {task_ref}"
    body = append_activity_entry(body, action_activity_entry(
        action=action, actor_label="actor", actor=actor, note=note))
    write_entity(issue_path, frontmatter=fm, body=body)
    _echo_touched(root, [issue_path])


@task_group.group("depend")
def task_depend_group() -> None:
    """Manage task dependencies."""


@task_depend_group.command("add")
@click.argument("task_ref")
@click.argument("depends_on_ref")
@click.option("--soft", is_flag=True, help="Add as a soft dependency (informational, not blocking).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_depend_add(
    ctx: click.Context,
    task_ref: str,
    depends_on_ref: str,
    soft: bool,
    actor: str,
    note: str | None,
) -> None:
    """Add a dependency to a task."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = add_task_dependency(
        root,
        task_ref=task_ref,
        depends_on_ref=depends_on_ref,
        actor=actor,
        soft=soft,
        note=note,
    )
    _echo_touched(root, [touched])


@task_depend_group.command("remove")
@click.argument("task_ref")
@click.argument("depends_on_ref")
@click.option("--soft", is_flag=True, help="Remove from soft dependencies.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_depend_remove(
    ctx: click.Context,
    task_ref: str,
    depends_on_ref: str,
    soft: bool,
    actor: str,
    note: str | None,
) -> None:
    """Remove a dependency from a task."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = remove_task_dependency(
        root,
        task_ref=task_ref,
        depends_on_ref=depends_on_ref,
        actor=actor,
        soft=soft,
        note=note,
    )
    _echo_touched(root, [touched])


@task_depend_group.command("bulk-add")
@click.argument("task_refs", nargs=-1)
@click.argument("depends_on_ref")
@click.option("--soft", is_flag=True, help="Add as a soft dependency.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_depend_bulk_add(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    depends_on_ref: str,
    soft: bool,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-add a dependency to multiple tasks."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        dep_type = "soft" if soft else "hard"
        click.echo(f"[DRY RUN] Would add {dep_type} dep {depends_on_ref!r} to {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = add_task_dependency(
                root,
                task_ref=task_ref,
                depends_on_ref=depends_on_ref,
                actor=actor,
                soft=soft,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_depend_group.command("bulk-remove")
@click.argument("task_refs", nargs=-1)
@click.argument("depends_on_ref")
@click.option("--soft", is_flag=True, help="Remove from soft dependencies.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_depend_bulk_remove(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    depends_on_ref: str,
    soft: bool,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-remove a dependency from multiple tasks."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        dep_type = "soft" if soft else "hard"
        click.echo(f"[DRY RUN] Would remove {dep_type} dep {depends_on_ref!r} from {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = remove_task_dependency(
                root,
                task_ref=task_ref,
                depends_on_ref=depends_on_ref,
                actor=actor,
                soft=soft,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("normalize-statuses")
@click.option("--write", "write_changes", is_flag=True, help="Rewrite legacy statuses in task files.")
@click.pass_context
def task_normalize_statuses(ctx: click.Context, write_changes: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    normalizations = normalize_task_statuses(root, write=write_changes)
    if not normalizations:
        click.echo("No legacy task statuses found.")
        return
    for item in normalizations:
        suffix = " updated" if item.changed else " dry-run"
        click.echo(f"{item.task_id} {item.old_status} -> {item.new_status}{suffix}")


@task_group.command("close")
@click.argument("task_ref")
@click.option("--closer", required=True)
@click.option("--note", required=True)
@click.pass_context
def task_close(ctx: click.Context, task_ref: str, closer: str, note: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = close_task(root, task_ref=task_ref, closer=closer, note=note)
    _echo_touched(root, [touched])
    try:
        open_issues = linked_open_issues_for_task(root, touched)
    except TrailmindError as exc:
        click.echo(f"linked issue report skipped: {exc.format_message()}")
        return
    if open_issues:
        details = ", ".join(f"{issue.issue_id} {issue.title}" for issue in open_issues)
        click.echo(f"linked open issues remain: {details}")


@task_group.command("bulk-close")
@click.argument("task_refs", nargs=-1)
@click.option("--closer", required=True)
@click.option("--note", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_bulk_close(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    closer: str,
    note: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-close tasks (e.g. T-001 T-002, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would close {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = close_task(root, task_ref=task_ref, closer=closer, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_group.command("pickup")
@click.argument("task_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.option("--log", "write_log", is_flag=True, help="Record an explicit pickup Activity Log entry.")
@click.option("--actor", default=None, help="Actor for --log.")
@click.option("--max-lines", default=80, show_default=True, type=click.IntRange(min=1))
@click.option("--activity-limit", default=10, show_default=True, type=click.IntRange(min=1))
@click.option("--no-excerpts", is_flag=True, help="List referenced paths without file contents.")
@click.pass_context
def task_pickup(
    ctx: click.Context,
    task_ref: str,
    json_output: bool,
    write_log: bool,
    actor: str | None,
    max_lines: int,
    activity_limit: int,
    no_excerpts: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if write_log and (not actor or not actor.strip()):
        raise TrailmindError("pickup logging requires --actor")
    pack = build_task_pickup(
        root,
        task_ref=task_ref,
        max_lines=max_lines,
        activity_limit=activity_limit,
        include_excerpts=not no_excerpts,
    )
    if json_output:
        click.echo(json.dumps(pickup_pack_to_dict(pack), ensure_ascii=False, indent=2))
        output_format = "json"
    else:
        click.echo(format_pickup_markdown(pack), nl=False)
        output_format = "markdown"
    if write_log and actor:
        log_task_pickup(root, task_ref=task_ref, actor=actor, output_format=output_format)


@task_group.group("deliverable")
def task_deliverable_group() -> None:
    """Manage task deliverables."""


@task_deliverable_group.command("add")
@click.argument("task_ref")
@click.option("--item", required=True)
@click.option("--actor", required=True)
@click.pass_context
def task_deliverable_add(ctx: click.Context, task_ref: str, item: str, actor: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = add_task_deliverable(root, task_ref=task_ref, item=item, actor=actor)
    _echo_touched(root, [touched])


@task_deliverable_group.command("complete")
@click.argument("task_ref")
@click.option("--item", required=True)
@click.option("--actor", required=True)
@click.pass_context
def task_deliverable_complete(ctx: click.Context, task_ref: str, item: str, actor: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = complete_task_deliverable(root, task_ref=task_ref, item=item, actor=actor)
    _echo_touched(root, [touched])


@task_deliverable_group.command("bulk-add")
@click.argument("task_refs", nargs=-1)
@click.option("--item", required=True)
@click.option("--actor", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_deliverable_bulk_add(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    item: str,
    actor: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-add a deliverable to multiple tasks."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would add deliverable {item!r} to {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = add_task_deliverable(root, task_ref=task_ref, item=item, actor=actor)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@task_deliverable_group.command("bulk-complete")
@click.argument("task_refs", nargs=-1)
@click.option("--item", required=True)
@click.option("--actor", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read task IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def task_deliverable_bulk_complete(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    item: str,
    actor: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-complete a deliverable on multiple tasks."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(task_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no task IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would complete deliverable {item!r} on {len(refs)} task(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for task_ref in refs:
        try:
            path = complete_task_deliverable(root, task_ref=task_ref, item=item, actor=actor)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {task_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@cli.group("issue")
def issue_group() -> None:
    """Manage issues."""


@issue_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, type=click.Choice(("open", "done", "wontfix"), case_sensitive=False),
              help="Filter by issue status.")
@click.option("--active", is_flag=True, help="Show only active issues (not done or wontfix).")
@click.option("--severity", default=None, type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False),
              help="Filter by severity.")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--unassigned", is_flag=True, help="Show only issues without an owner.")
@click.option("--has-linked-tasks", is_flag=True, help="Show only issues that have linked tasks.")
@click.option("--no-linked-tasks", is_flag=True, help="Show only issues without linked tasks.")
@click.option("--created-since", default=None, help="Filter issues created on or after YYYY-MM-DD.")
@click.option("--created-before", default=None, help="Filter issues created before YYYY-MM-DD.")
@click.option("--created-today", is_flag=True, help="Show only issues created today.")
@click.option("--created-this-week", is_flag=True, help="Show only issues created this week.")
@click.option("--title-contains", default=None, help="Filter by title substring (case-insensitive).")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "severity", "status", "title"), case_sensitive=False),
              help="Sort issues (default: created).")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "severity", "owner", "epic", "project"), case_sensitive=False),
              help="Group issues by status, severity, owner, epic, or project.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--ids", "ids_only", is_flag=True, help="Output only entity IDs (one per line, for piping).")
@click.option("--count", "count_only", is_flag=True, help="Show only the count of matching issues.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV for spreadsheet import.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def issue_list_cmd(
    ctx: click.Context,
    epic_ref: str | None,
    project_ref: str | None,
    status: str | None,
    active: bool,
    severity: str | None,
    owner: str | None,
    unassigned: bool,
    has_linked_tasks: bool,
    no_linked_tasks: bool,
    created_since: str | None,
    created_before: str | None,
    created_today: bool,
    created_this_week: bool,
    title_contains: str | None,
    sort_by: str,
    group_by: str | None,
    compact: bool,
    ids_only: bool,
    count_only: bool,
    csv_output: bool,
    limit: int | None,
    json_output: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    issues = list_issues(root, epic_ref=epic_ref, project_ref=project_ref,
                          status=status, severity=severity, owner=owner, sort_by=sort_by)
    if active:
        issues = [i for i in issues if i.get("status") not in ("done", "wontfix")]
    if unassigned:
        issues = [i for i in issues if not i.get("owner")]
    if has_linked_tasks:
        issues = [i for i in issues if i.get("linked_tasks")]
    if no_linked_tasks:
        issues = [i for i in issues if not i.get("linked_tasks")]
    if title_contains:
        needle = title_contains.lower()
        issues = [i for i in issues if needle in (i.get("title") or "").lower()]
    # --created-today and --created-this-week shortcuts
    if created_today or created_this_week:
        from datetime import date, timedelta
        today = date.today()
        if created_today:
            today_str = today.isoformat()
            issues = [i for i in issues if i.get("created") == today_str]
        elif created_this_week:
            week_start = today - timedelta(days=today.weekday())
            week_start_str = week_start.isoformat()
            issues = [i for i in issues if i.get("created") and i["created"] >= week_start_str]
    if created_since:
        issues = [i for i in issues if i.get("created") and i["created"] >= created_since]
    if created_before:
        issues = [i for i in issues if i.get("created") and i["created"] < created_before]
    if ids_only:
        for i in issues:
            click.echo(i.get("id", ""))
        return
    if count_only:
        click.echo(f"{len(issues)} issue{'s' if len(issues) != 1 else ''}")
        return
    if limit:
        issues = issues[:limit]

    if csv_output:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "title", "status", "severity", "owner", "filer", "created", "path"])
        for i in issues:
            writer.writerow([
                i.get("id", ""), i.get("title", ""), i.get("status", ""),
                i.get("severity", ""), i.get("owner", ""), i.get("filer", ""),
                i.get("created", ""), i.get("path", ""),
            ])
        click.echo(output.getvalue(), nl=False)
        return

    if json_output:
        click.echo(json.dumps(issues, ensure_ascii=False, indent=2))
        return

    if not issues:
        click.echo("No issues.")
        return

    if group_by:
        from collections import defaultdict
        groups: dict[str, list[dict]] = defaultdict(list)
        for i in issues:
            if group_by == "epic":
                key = i.get("epic", "") or "unknown"
            elif group_by == "project":
                epic_path = i.get("epic", "") or ""
                parts = epic_path.split("/")
                key = parts[1] if len(parts) > 1 else "unknown"
            else:
                key = i.get(group_by, "") or "unassigned"
            groups[key].append(i)

        if group_by == "severity":
            sev_order = {s: i for i, s in enumerate(("critical", "high", "medium", "low", ""))}
            sorted_keys = sorted(groups.keys(), key=lambda k: sev_order.get(k, 99))
        elif group_by == "status":
            st_order = {s: i for i, s in enumerate(("open", "in_progress", "done", "wontfix"))}
            sorted_keys = sorted(groups.keys(), key=lambda k: st_order.get(k, 99))
        else:
            sorted_keys = sorted(groups.keys())

        for key in sorted_keys:
            group_issues = groups[key]
            display_key = key
            if group_by == "epic":
                display_key = key.split("/")[-1] if "/" in key else key
            click.echo(f"\n{display_key.upper()} ({len(group_issues)})")
            click.echo("─" * 60)
            for i in group_issues:
                sev = f" [{i['severity']}]" if i['severity'] else ""
                owner_str = f" @{i['owner']}" if i.get('owner') else ""
                if compact:
                    click.echo(f"  {i['id']:16s} {i['status']:10s}{sev}{owner_str} {i['title']}")
                else:
                    click.echo(f"  {i['id']:16s} {i['status']:10s}{sev}{owner_str} {i['title']}")
                    click.echo(f"  {'':16s} {'':10s}  {i['path']}")
    else:
        for i in issues:
            sev = f" [{i['severity']}]" if i['severity'] else ""
            owner_str = f" @{i['owner']}" if i.get('owner') else ""
            if compact:
                click.echo(f"{i['id']:16s} {i['status']:10s}{sev}{owner_str} {i['title']}")
            else:
                click.echo(f"{i['id']:16s} {i['status']:10s}{sev}{owner_str} {i['title']}")
                click.echo(f"{'':16s} {'':10s}  {i['path']}")


@issue_group.command("add")
@click.option("--epic", required=True)
@click.option("--filer", required=True)
@click.option("--owner", default=None, help="Owner email or shortname (defaults to filer).")
@click.option("--title", required=True)
@click.option("--description", default="TBD", help="Issue description (default: TBD).")
@click.option("--severity", required=True)
@click.option("--linked-tasks", default=None, help="Comma-separated linked task IDs or refs.")
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def issue_add(
    ctx: click.Context,
    epic: str,
    filer: str,
    owner: str | None,
    title: str,
    description: str,
    severity: str,
    linked_tasks: str | None,
    dry_run: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would create issue in {epic}:")
        click.echo(f"  Title: {title}")
        click.echo(f"  Filer: {filer}, Owner: {owner or filer}")
        click.echo(f"  Severity: {severity}")
        if linked_tasks:
            click.echo(f"  Linked tasks: {linked_tasks}")
        return
    linked = split_csv(linked_tasks) if linked_tasks else None
    touched = add_issue(root, epic=epic, filer=filer, owner=owner, title=title,
                         description=description, severity=severity, linked_tasks=linked)
    _echo_touched(root, [touched])


@issue_group.command("bulk-add")
@click.option("--epic", required=True)
@click.option("--filer", required=True)
@click.option("--input-file", "input_file", required=True,
              help="CSV or JSON file with issues (columns: title, owner, severity, description, linked_tasks).")
@click.option("--format", "fmt", default="csv", type=click.Choice(("csv", "json"), case_sensitive=False),
              help="Input file format (default: csv).")
@click.option("--default-owner", default=None, help="Default owner if not specified in file.")
@click.option("--default-severity", default="medium", show_default=True,
              type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False),
              help="Default severity if not specified in file.")
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def issue_bulk_add(
    ctx: click.Context,
    epic: str,
    filer: str,
    input_file: str,
    fmt: str,
    default_owner: str | None,
    default_severity: str,
    dry_run: bool,
) -> None:
    """Bulk-add issues from a CSV or JSON file."""
    import csv
    import json as _json
    root = find_repo_root(_cwd_from_context(ctx))

    path = Path(input_file)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise TrailmindError(f"input file not found: {input_file}")

    content = path.read_text(encoding="utf-8")

    issue_specs: list[dict] = []
    if fmt == "json":
        data = _json.loads(content)
        if isinstance(data, list):
            issue_specs = data
        elif isinstance(data, dict) and "issues" in data:
            issue_specs = data["issues"]
        else:
            raise TrailmindError("JSON must be a list or object with 'issues' key.")
    else:
        reader = csv.DictReader(content.splitlines())
        for row in reader:
            issue_specs.append(dict(row))

    if not issue_specs:
        raise TrailmindError("no issues found in input file")

    if dry_run:
        click.echo(f"[DRY RUN] Would create {len(issue_specs)} issue(s) in {epic}:")
        for i, spec in enumerate(issue_specs):
            title = spec.get("title", "(untitled)")
            owner = spec.get("owner") or default_owner or "(unassigned)"
            severity = spec.get("severity") or default_severity
            click.echo(f"  {i+1}. {title} (owner: @{owner}, severity: {severity})")
        return

    touched = []
    for i, spec in enumerate(issue_specs):
        title = spec.get("title", "").strip()
        if not title:
            click.echo(f"  ⚠ issue {i+1}: missing title, skipping", err=True)
            continue
        owner = spec.get("owner") or default_owner
        severity = spec.get("severity") or default_severity
        description = spec.get("description") or "TBD"
        linked_str = spec.get("linked_tasks") or ""
        linked = split_csv(linked_str) if linked_str else None

        try:
            path = add_issue(
                root,
                epic=epic,
                filer=filer,
                owner=owner,
                title=title,
                description=description,
                severity=severity,
                linked_tasks=linked,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {title}: {exc}", err=True)

    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nCreated {len(touched)}/{len(issue_specs)} issues.")


@issue_group.command("link")
@click.option("--issue", "issue_ref", required=True)
@click.option("--task", "task_ref", required=True)
@click.pass_context
def issue_link(ctx: click.Context, issue_ref: str, task_ref: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = link_issue(root, raw_issue=issue_ref, raw_task=task_ref)
    _echo_touched(root, touched)


@issue_group.command("close")
@click.argument("issue_ref")
@click.option("--closer", required=True)
@click.option("--status", required=True)
@click.option("--note", required=True)
@click.pass_context
def issue_close(ctx: click.Context, issue_ref: str, closer: str, status: str, note: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = close_issue(root, raw_id=issue_ref, closer=closer, status=status, note=note)
    _echo_touched(root, [touched])


@issue_group.command("bulk-close")
@click.argument("issue_refs", nargs=-1)
@click.option("--closer", required=True)
@click.option("--status", required=True, type=click.Choice(("done", "wontfix"), case_sensitive=False))
@click.option("--note", required=True)
@click.option("--from-file", "from_file", default=None,
              help="Read issue IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_bulk_close(
    ctx: click.Context,
    issue_refs: tuple[str, ...],
    closer: str,
    status: str,
    note: str,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-close issues (e.g. I-001 I-002, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would close {len(refs)} issue(s) as {status!r}:")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for issue_ref in refs:
        try:
            path = close_issue(root, raw_id=issue_ref, closer=closer, status=status, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@issue_group.command("carry")
@click.option("--issue", "issue_ref", required=True)
@click.option("--to-epic", required=True)
@click.pass_context
def issue_carry(ctx: click.Context, issue_ref: str, to_epic: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = carry_issue(root, raw_issue=issue_ref, to_epic=to_epic)
    _echo_touched(root, touched)


@issue_group.command("move")
@click.argument("issue_ref")
@click.argument("target_epic")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_move(
    ctx: click.Context,
    issue_ref: str,
    target_epic: str,
    actor: str,
    note: str | None,
) -> None:
    """Move an issue to a different epic (e.g. projects/demo/new_epic)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = move_issue(
        root,
        issue_ref=issue_ref,
        target_epic=target_epic,
        actor=actor,
        note=note,
    )
    _echo_touched(root, [touched])


@issue_group.command("rename")
@click.argument("issue_ref")
@click.argument("new_title")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_rename(
    ctx: click.Context,
    issue_ref: str,
    new_title: str,
    actor: str,
    note: str | None,
) -> None:
    """Rename an issue (updates title and filename)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = rename_issue(
        root,
        issue_ref=issue_ref,
        new_title=new_title,
        actor=actor,
        note=note,
    )
    _echo_touched(root, [touched])


@issue_group.command("clone")
@click.argument("issue_ref")
@click.option("--title", default=None, help="New issue title (defaults to source title).")
@click.option("--owner", default=None, help="New owner email/shortname (defaults to actor).")
@click.option("--to-epic", "target_epic", default=None, help="Target epic (defaults to source epic).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_clone(
    ctx: click.Context,
    issue_ref: str,
    title: str | None,
    owner: str | None,
    target_epic: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Clone an issue, preserving severity and linked tasks."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = clone_issue(
        root,
        issue_ref=issue_ref,
        actor=actor,
        title=title,
        owner=owner,
        target_epic=target_epic,
        note=note,
    )
    _echo_touched(root, [touched])


@issue_group.command("show")
@click.argument("issue_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def issue_show(ctx: click.Context, issue_ref: str, json_output: bool) -> None:
    """Show details of a single issue."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = show_entity(root, issue_ref, "I")
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Issue"), nl=False)


@issue_group.command("comment")
@click.argument("issue_ref")
@click.option("--author", required=True, help="Author email or shortname.")
@click.option("--text", required=True, help="Comment text.")
@click.pass_context
def issue_comment(ctx: click.Context, issue_ref: str, author: str, text: str) -> None:
    """Add a dated, attributed comment to an issue."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = comment_issue(root, issue_ref=issue_ref, author=author, text=text)
    _echo_touched(root, [touched])


@issue_group.command("assign")
@click.argument("issue_ref")
@click.argument("owner")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_assign(
    ctx: click.Context,
    issue_ref: str,
    owner: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Reassign an issue to a different owner."""
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would assign {issue_ref} to @{owner}")
        return
    touched = assign_issue(root, issue_ref=issue_ref, owner=owner, actor=actor, note=note)
    _echo_touched(root, [touched])


@issue_group.command("set-severity")
@click.argument("issue_ref")
@click.argument("severity", type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_set_severity(
    ctx: click.Context,
    issue_ref: str,
    severity: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Change an issue's severity."""
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would set {issue_ref} severity to {severity!r}")
        return
    touched = set_issue_severity(root, issue_ref=issue_ref, severity=severity, actor=actor, note=note)
    _echo_touched(root, [touched])


@issue_group.command("bulk-severity")
@click.argument("issue_refs", nargs=-1)
@click.argument("severity", type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read issue IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_bulk_severity(
    ctx: click.Context,
    issue_refs: tuple[str, ...],
    severity: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-set severity for issues (e.g. I-001 I-002 high, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set severity to {severity!r} for {len(refs)} issue(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for issue_ref in refs:
        try:
            path = set_issue_severity(root, issue_ref=issue_ref, severity=severity, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@issue_group.command("bulk-status")
@click.argument("issue_refs", nargs=-1)
@click.argument("status", type=click.Choice(("open", "done", "wontfix"), case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read issue IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.pass_context
def issue_bulk_status(
    ctx: click.Context,
    issue_refs: tuple[str, ...],
    status: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-update issue status (e.g. I-001 I-002 done, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set status to {status!r} for {len(refs)} issue(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    root = find_repo_root(_cwd_from_context(ctx))
    touched = []
    for issue_ref in refs:
        try:
            if status in ("done", "wontfix"):
                path = close_issue(
                    root,
                    issue_ref=issue_ref,
                    closer=actor,
                    status=status,
                    note=note or f"Bulk closed as {status}",
                )
            else:  # open
                path = reopen_issue(
                    root,
                    issue_ref=issue_ref,
                    actor=actor,
                    note=note,
                )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@issue_group.command("bulk-assign")
@click.argument("issue_refs", nargs=-1)
@click.argument("owner")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read issue IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.pass_context
def issue_bulk_assign(
    ctx: click.Context,
    issue_refs: tuple[str, ...],
    owner: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-assign issues to an owner (e.g. I-001 I-002 alice, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would assign {len(refs)} issue(s) to @{owner}:")
        for r in refs:
            click.echo(f"  - {r}")
        return
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    touched = []
    for issue_ref in refs:
        try:
            path = assign_issue(
                root,
                issue_ref=issue_ref,
                owner=owner,
                actor=actor,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@issue_group.command("edit")
@click.argument("issue_ref")
@click.option("--title", default=None, help="New issue title.")
@click.option("--description", default=None, help="New issue description.")
@click.option("--severity", default=None, type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False),
              help="New issue severity.")
@click.option("--owner", default=None, help="New owner email or shortname.")
@click.option("--linked-tasks", default=None, help="Comma-separated linked task IDs (replaces existing).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_edit(
    ctx: click.Context,
    issue_ref: str,
    title: str | None,
    description: str | None,
    severity: str | None,
    owner: str | None,
    linked_tasks: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on an issue."""
    root = find_repo_root(_cwd_from_context(ctx))
    linked = split_csv(linked_tasks) if linked_tasks is not None else None
    touched = edit_issue(
        root,
        issue_ref=issue_ref,
        actor=actor,
        title=title,
        description=description,
        severity=severity,
        owner=owner,
        linked_tasks=linked,
        note=note,
    )
    _echo_touched(root, [touched])


@issue_group.command("bulk-edit")
@click.option("--input-file", "input_file", required=True,
              help="CSV or JSON file with issue edits (must have 'id' column; optional: title, description, severity, owner, linked_tasks).")
@click.option("--format", "fmt", default="csv", type=click.Choice(("csv", "json"), case_sensitive=False),
              help="Input file format (default: csv).")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_bulk_edit(
    ctx: click.Context,
    input_file: str,
    fmt: str,
    actor: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Bulk-edit issues from a CSV or JSON file (identified by 'id' column)."""
    import csv
    import json as _json
    root = find_repo_root(_cwd_from_context(ctx))

    path = Path(input_file)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise TrailmindError(f"input file not found: {input_file}")

    content = path.read_text(encoding="utf-8")

    edit_specs: list[dict] = []
    if fmt == "json":
        data = _json.loads(content)
        if isinstance(data, list):
            edit_specs = data
        elif isinstance(data, dict) and "issues" in data:
            edit_specs = data["issues"]
        else:
            raise TrailmindError("JSON must be a list or object with 'issues' key.")
    else:
        reader = csv.DictReader(content.splitlines())
        for row in reader:
            edit_specs.append(dict(row))

    if not edit_specs:
        raise TrailmindError("no issue edits found in input file")

    if dry_run:
        click.echo(f"[DRY RUN] Would edit {len(edit_specs)} issue(s):")
        for i, spec in enumerate(edit_specs):
            issue_id = spec.get("id", "(no id)")
            changes = []
            for key in ("title", "description", "severity", "owner", "linked_tasks"):
                if key in spec and spec[key]:
                    changes.append(f"{key}={spec[key]}")
            click.echo(f"  {i+1}. {issue_id}: {', '.join(changes) if changes else '(no changes)'}")
        return

    touched = []
    for i, spec in enumerate(edit_specs):
        issue_id = spec.get("id", "").strip()
        if not issue_id:
            click.echo(f"  ⚠ edit {i+1}: missing id, skipping", err=True)
            continue

        title = spec.get("title") or None
        description = spec.get("description") or None
        severity = spec.get("severity") or None
        owner = spec.get("owner") or None
        linked_str = spec.get("linked_tasks")
        linked = split_csv(linked_str) if linked_str is not None else None

        try:
            path = edit_issue(
                root,
                issue_ref=issue_id,
                actor=actor,
                title=title,
                description=description,
                severity=severity,
                owner=owner,
                linked_tasks=linked,
                note=note,
            )
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_id}: {exc}", err=True)

    if touched:
        _echo_touched(root, touched)
        click.echo(f"\nEdited {len(touched)}/{len(edit_specs)} issues.")


@issue_group.command("reopen")
@click.argument("issue_ref")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_reopen(
    ctx: click.Context,
    issue_ref: str,
    actor: str,
    note: str | None,
) -> None:
    """Reopen a closed issue (done or wontfix → open)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = reopen_issue(root, issue_ref=issue_ref, actor=actor, note=note)
    _echo_touched(root, [touched])


@issue_group.command("bulk-reopen")
@click.argument("issue_refs", nargs=-1)
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read issue IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def issue_bulk_reopen(
    ctx: click.Context,
    issue_refs: tuple[str, ...],
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-reopen closed issues (e.g. I-001 I-002, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(issue_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no issue IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would reopen {len(refs)} issue(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for issue_ref in refs:
        try:
            path = reopen_issue(root, issue_ref=issue_ref, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {issue_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@issue_group.command("pickup")
@click.argument("issue_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.option("--log", "write_log", is_flag=True, help="Record an explicit pickup Activity Log entry.")
@click.option("--actor", default=None, help="Actor for --log.")
@click.option("--max-lines", default=80, show_default=True, type=click.IntRange(min=1))
@click.option("--activity-limit", default=10, show_default=True, type=click.IntRange(min=1))
@click.option("--no-excerpts", is_flag=True, help="List referenced paths without file contents.")
@click.pass_context
def issue_pickup(
    ctx: click.Context,
    issue_ref: str,
    json_output: bool,
    write_log: bool,
    actor: str | None,
    max_lines: int,
    activity_limit: int,
    no_excerpts: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if write_log and (not actor or not actor.strip()):
        raise TrailmindError("pickup logging requires --actor")
    pack = build_issue_pickup(
        root,
        issue_ref=issue_ref,
        max_lines=max_lines,
        activity_limit=activity_limit,
        include_excerpts=not no_excerpts,
    )
    if json_output:
        click.echo(json.dumps(pickup_pack_to_dict(pack), ensure_ascii=False, indent=2))
        output_format = "json"
    else:
        click.echo(format_pickup_markdown(pack), nl=False)
        output_format = "markdown"
    if write_log and actor:
        log_issue_pickup(root, issue_ref=issue_ref, actor=actor, output_format=output_format)


@cli.group("milestone")
def milestone_group() -> None:
    """Manage milestones."""


@milestone_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, type=click.Choice(("planned", "in_progress", "done"), case_sensitive=False),
              help="Filter by milestone status.")
@click.option("--active", is_flag=True, help="Show only active milestones (not done).")
@click.option("--upcoming", is_flag=True, help="Show only upcoming milestones (date >= today, not done).")
@click.option("--due-within", "due_within_days", default=None, type=click.IntRange(min=0),
              help="Show milestones due within N days (not done).")
@click.option("--sort", "sort_by", default="date",
              type=click.Choice(("date", "created", "status", "title"), case_sensitive=False),
              help="Sort milestones (default: date).")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "epic", "project"), case_sensitive=False),
              help="Group milestones by status, epic, or project.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--ids", "ids_only", is_flag=True, help="Output only entity IDs (one per line, for piping).")
@click.option("--count", "count_only", is_flag=True, help="Show only the count of matching milestones.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def milestone_list_cmd(ctx: click.Context, epic_ref: str | None, project_ref: str | None,
                        status: str | None, active: bool, upcoming: bool, due_within_days: int | None,
                        sort_by: str, group_by: str | None,
                        limit: int | None, compact: bool, ids_only: bool, count_only: bool, csv_output: bool, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    milestones = list_milestones(root, epic_ref=epic_ref, project_ref=project_ref,
                                  status=status, sort_by=sort_by)
    if active:
        milestones = [m for m in milestones if m.get("status") != "done"]
    if upcoming:
        from datetime import date
        today = date.today().isoformat()
        milestones = [m for m in milestones
                      if m.get("date") and m["date"] >= today and m.get("status") != "done"]
    if due_within_days is not None:
        from datetime import date, timedelta
        today = date.today()
        within = (today + timedelta(days=due_within_days)).isoformat()
        today_str = today.isoformat()
        milestones = [m for m in milestones
                      if m.get("date") and today_str <= m["date"] <= within and m.get("status") != "done"]
    if ids_only:
        for m in milestones:
            click.echo(m.get("id", ""))
        return
    if count_only:
        click.echo(f"{len(milestones)} milestone{'s' if len(milestones) != 1 else ''}")
        return
    if limit:
        milestones = milestones[:limit]
    if csv_output:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "title", "status", "date", "created", "epic", "path"])
        for m in milestones:
            writer.writerow([m.get("id", ""), m.get("title", ""), m.get("status", ""),
                            m.get("date", ""), m.get("created", ""), m.get("epic", ""), m.get("path", "")])
        click.echo(output.getvalue(), nl=False)
        return
    if json_output:
        click.echo(json.dumps(milestones, ensure_ascii=False, indent=2))
        return

    if not milestones:
        click.echo("No milestones.")
        return

    if group_by:
        from collections import defaultdict
        groups: dict[str, list[dict]] = defaultdict(list)
        for m in milestones:
            if group_by == "epic":
                key = m.get("epic", "") or "unknown"
            elif group_by == "project":
                epic = m.get("epic", "") or ""
                parts = epic.split("/")
                key = parts[1] if len(parts) > 1 else "unknown"
            else:
                key = m.get(group_by, "") or "unknown"
            groups[key].append(m)

        if group_by == "status":
            st_order = {"in_progress": 0, "planned": 1, "done": 2}
            sorted_keys = sorted(groups.keys(), key=lambda k: st_order.get(k, 99))
        else:
            sorted_keys = sorted(groups.keys())

        for key in sorted_keys:
            group_ms = groups[key]
            display_key = key
            if group_by == "epic":
                display_key = key.split("/")[-1] if "/" in key else key
            click.echo(f"\n{display_key.upper()} ({len(group_ms)})")
            click.echo("─" * 60)
            for m in group_ms:
                click.echo(f"  {m['id']:12s} {m['status']:12s} {m['date']:12s} {m['title']}")
                click.echo(f"  {'':12s} {'':12s} {'':12s} {m['path']}")
    else:
        for m in milestones:
            if compact:
                click.echo(f"{m['id']:12s} {m['status']:12s} {m['date']:12s} {m['title']}")
            else:
                click.echo(f"{m['id']:12s} {m['status']:12s} {m['date']:12s} {m['title']}")
                click.echo(f"{'':12s} {'':12s} {'':12s} {m['path']}")


@milestone_group.command("set-status")
@click.argument("milestone_ref")
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def milestone_set_status(ctx: click.Context, milestone_ref: str, status: str, actor: str, note: str | None, dry_run: bool) -> None:
    """Change a milestone's status (planned, in_progress, done)."""
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would set {milestone_ref} status to {status!r}")
        return
    touched = set_milestone_status(root, milestone_ref=milestone_ref, status=status, actor=actor, note=note)
    _echo_touched(root, [touched])


@milestone_group.command("bulk-set-status")
@click.argument("milestone_refs", nargs=-1)
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--from-file", "from_file", default=None,
              help="Read milestone IDs from file (one per line), or '-' for stdin.")
@click.option("--dry-run", is_flag=True, help="Preview without applying.")
@click.pass_context
def milestone_bulk_set_status(
    ctx: click.Context,
    milestone_refs: tuple[str, ...],
    status: str,
    actor: str,
    note: str | None,
    from_file: str | None,
    dry_run: bool,
) -> None:
    """Bulk-set milestone status (e.g. M-001 M-002 done, or --from-file ids.txt)."""
    root = find_repo_root(_cwd_from_context(ctx))
    refs = list(milestone_refs)
    if from_file:
        refs.extend(_read_ids_from_file(from_file))
    if not refs:
        raise TrailmindError("no milestone IDs provided (pass as args or use --from-file)")
    if dry_run:
        click.echo(f"[DRY RUN] Would set status to {status!r} for {len(refs)} milestone(s):")
        for r in refs:
            click.echo(f"  - {r}")
        return
    touched = []
    for milestone_ref in refs:
        try:
            path = set_milestone_status(root, milestone_ref=milestone_ref, status=status, actor=actor, note=note)
            touched.append(path)
        except Exception as exc:
            click.echo(f"  ⚠ {milestone_ref}: {exc}", err=True)
    if touched:
        _echo_touched(root, touched)


@milestone_group.command("add")
@click.option("--epic", required=True)
@click.option("--title", required=True)
@click.option("--date", "milestone_date", required=True)
@click.option("--dry-run", is_flag=True, help="Preview without creating.")
@click.pass_context
def milestone_add(ctx: click.Context, epic: str, title: str, milestone_date: str, dry_run: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    if dry_run:
        click.echo(f"[DRY RUN] Would create milestone in {epic}:")
        click.echo(f"  Title: {title}")
        click.echo(f"  Date: {milestone_date}")
        return
    touched = add_milestone(root, epic=epic, title=title, milestone_date=milestone_date)
    _echo_touched(root, [touched])


@milestone_group.command("show")
@click.argument("milestone_ref")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def milestone_show(ctx: click.Context, milestone_ref: str, json_output: bool) -> None:
    """Show details of a single milestone."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = show_entity(root, milestone_ref, "M")
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_entity_show(data, entity_label="Milestone"), nl=False)


@milestone_group.command("edit")
@click.argument("milestone_ref")
@click.option("--title", default=None, help="New milestone title.")
@click.option("--date", "milestone_date", default=None, help="New milestone date (YYYY-MM-DD).")
@click.option("--status", default=None, type=click.Choice(MILESTONE_STATUSES, case_sensitive=False),
              help="New milestone status.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def milestone_edit(
    ctx: click.Context,
    milestone_ref: str,
    title: str | None,
    milestone_date: str | None,
    status: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on a milestone."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = edit_milestone(
        root,
        milestone_ref=milestone_ref,
        actor=actor,
        title=title,
        milestone_date=milestone_date,
        status=status,
        note=note,
    )
    _echo_touched(root, [touched])


@cli.command("activity")
@click.option("--limit", default=20, show_default=True, type=click.IntRange(min=1, max=200),
              help="Maximum entries to show.")
@click.option("--type", "entity_type", default=None,
              type=click.Choice(("project", "epic", "task", "issue", "milestone", "inbox", "spec", "plan"),
                             case_sensitive=False),
              help="Filter by entity type.")
@click.option("--actor", default=None, help="Filter by actor shortname.")
@click.option("--since", default=None, help="Show entries since YYYY-MM-DD.")
@click.option("--project", default=None, help="Filter by project slug.")
@click.option("--epic", default=None, help="Filter by epic path or slug.")
@click.option("--sort", "sort_by", default="date",
              type=click.Choice(("date", "entity_type", "actor", "action"), case_sensitive=False),
              help="Sort entries (default: date).")
@click.option("--group-by", default=None,
              type=click.Choice(("entity_type", "actor", "date"), case_sensitive=False),
              help="Group activity by entity type, actor, or date.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def activity_command(
    ctx: click.Context,
    limit: int,
    entity_type: str | None,
    actor: str | None,
    since: str | None,
    project: str | None,
    epic: str | None,
    sort_by: str,
    group_by: str | None,
    compact: bool,
    csv_output: bool,
    json_output: bool,
) -> None:
    """Show recent activity across all entities."""
    root = find_repo_root(_cwd_from_context(ctx))
    entries = collect_activity(
        root,
        limit=limit,
        entity_type=entity_type,
        actor=actor,
        since=since,
        project=project,
        epic=epic,
    )

    # Sort
    if sort_by != "date":
        if sort_by == "entity_type":
            entries.sort(key=lambda e: (e.get("entity_type", ""), e.get("date", "")), reverse=True)
        elif sort_by == "actor":
            entries.sort(key=lambda e: (e.get("actor", ""), e.get("date", "")), reverse=True)
        elif sort_by == "action":
            entries.sort(key=lambda e: (e.get("action", "").lower(), e.get("date", "")), reverse=True)

    if csv_output:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "entity_type", "entity_id", "entity_title", "actor", "action", "note"])
        for e in entries:
            writer.writerow([
                e.get("date", ""), e.get("entity_type", ""), e.get("entity_id", ""),
                e.get("entity_title", ""), e.get("actor", ""), e.get("action", ""),
                e.get("note", ""),
            ])
        click.echo(output.getvalue(), nl=False)
        return

    if json_output:
        click.echo(json.dumps(entries, ensure_ascii=False, indent=2))
        return

    if not entries:
        click.echo("No activity found.")
        return

    if group_by:
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for e in entries:
            if group_by == "entity_type":
                key = e.get("entity_type", "unknown")
            elif group_by == "actor":
                key = e.get("actor", "unknown")
            else:  # date
                key = e.get("date", "unknown")
            groups[key].append(e)

        if group_by == "entity_type":
            et_order = {"task": 0, "issue": 1, "milestone": 2, "inbox": 3, "epic": 4, "project": 5, "spec": 6, "plan": 7}
            sorted_keys = sorted(groups.keys(), key=lambda k: et_order.get(k, 99))
        elif group_by == "actor":
            sorted_keys = sorted(groups.keys())
        else:
            sorted_keys = sorted(groups.keys(), reverse=True)

        type_icon_map = {
            "project": "📦", "epic": "🎯", "task": "✅", "issue": "🐛",
            "milestone": "🏁", "inbox": "📥", "spec": "📐", "plan": "📋",
        }

        for key in sorted_keys:
            group_entries = groups[key]
            display_key = key
            if group_by == "entity_type":
                icon = type_icon_map.get(key, "📄")
                display_key = f"{icon} {key}"
            elif group_by == "actor":
                display_key = f"👤 {key}"
            click.echo(f"\n{display_key} ({len(group_entries)})")
            click.echo("─" * 60)
            for e in group_entries:
                icon = type_icon_map.get(e["entity_type"], "📄")
                if compact:
                    note_str = f" — {e['note']}" if e["note"] else ""
                    click.echo(f"  {e['date']} {icon} {e['entity_id']:14s} {e['action']}{note_str}")
                else:
                    note_str = f" — {e['note']}" if e["note"] else ""
                    click.echo(f"  {e['date']}  {e['entity_id']:14s} {e['action']}{note_str}")
    else:
        for e in entries:
            type_icon = {
                "project": "📦", "epic": "🎯", "task": "✅", "issue": "🐛",
                "milestone": "🏁", "inbox": "📥", "spec": "📐", "plan": "📋",
            }.get(e["entity_type"], "📄")
            if compact:
                note_str = f" — {e['note']}" if e["note"] else ""
                click.echo(f"{e['date']} {type_icon} {e['entity_type']:10s} {e['entity_id']:14s} {e['actor']:10s} {e['action']}{note_str}")
            else:
                note_str = f" — {e['note']}" if e["note"] else ""
                click.echo(f"  {e['date']}  {type_icon} {e['action']}")
                click.echo(f"          by {e['actor']} on {e['entity_type']} {e['entity_id']} {e['entity_title']}{note_str}")
                click.echo()


@cli.command("search")
@click.argument("query")
@click.option("--type", "entity_types", default=None,
              help="Filter by entity type (comma-separated: task,issue,epic,project,milestone,inbox,spec,plan).")
@click.option("--project", default=None, help="Filter by project slug.")
@click.option("--epic", default=None, help="Filter by epic path or slug.")
@click.option("--group-by", default=None,
              type=click.Choice(("entity_type", "status"), case_sensitive=False),
              help="Group results by entity type or status.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--count", "count_only", is_flag=True, help="Show only the count.")
@click.option("--limit", default=30, show_default=True, type=click.IntRange(min=1, max=200),
              help="Maximum results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def search_command(
    ctx: click.Context,
    query: str,
    entity_types: str | None,
    project: str | None,
    epic: str | None,
    group_by: str | None,
    compact: bool,
    count_only: bool,
    limit: int,
    json_output: bool,
) -> None:
    """Search across all entities by keyword."""
    root = find_repo_root(_cwd_from_context(ctx))
    type_list = [t.strip().lower() for t in entity_types.split(",")] if entity_types else None
    results = search_entities(root, query=query, entity_types=type_list,
                               project=project, epic=epic, limit=limit)

    if count_only:
        click.echo(f"{len(results)} result{'s' if len(results) != 1 else ''}")
        return

    if json_output:
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        click.echo(f"No results found for {query!r}.")
        return

    type_icons = {
        "project": "📦", "epic": "🎯", "task": "✅", "issue": "🐛",
        "milestone": "🏁", "inbox": "📥", "spec": "📐", "plan": "📋",
    }

    if group_by:
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for r in results:
            if group_by == "entity_type":
                key = r["entity_type"]
            else:
                key = r.get("status") or "unknown"
            groups[key].append(r)

        if group_by == "entity_type":
            et_order = {"task": 0, "issue": 1, "milestone": 2, "inbox": 3, "epic": 4, "project": 5, "spec": 6, "plan": 7}
            sorted_keys = sorted(groups.keys(), key=lambda k: et_order.get(k, 99))
        else:
            sorted_keys = sorted(groups.keys())

        click.echo(f"Found {len(results)} result(s) for {query!r}:\n")
        for key in sorted_keys:
            group_results = groups[key]
            display_key = key
            if group_by == "entity_type":
                icon = type_icons.get(key, "📄")
                display_key = f"{icon} {key}"
            click.echo(f"{display_key.upper()} ({len(group_results)})")
            click.echo("─" * 60)
            for r in group_results:
                icon = type_icons.get(r["entity_type"], "📄")
                status_str = f" [{r['status']}]" if r["status"] else ""
                if compact:
                    click.echo(f"  {r['entity_id']:16s}{status_str}  {r['title']}")
                else:
                    click.echo(f"  {r['entity_id']:16s}{status_str}  {r['title']}")
                    click.echo(f"  {'':16s}  {r['path']}")
            click.echo()
    else:
        click.echo(f"Found {len(results)} result(s) for {query!r}:\n")
        for r in results:
            icon = type_icons.get(r["entity_type"], "📄")
            status_str = f" [{r['status']}]" if r["status"] else ""
            if compact:
                click.echo(f"  {icon} {r['entity_type']:10s} {r['entity_id']:16s}{status_str}  {r['title']}")
            else:
                click.echo(f"  {icon} {r['entity_type']:10s} {r['entity_id']:16s}{status_str}  {r['title']}")
                if r["snippet"]:
                    snippet = r["snippet"]
                    if len(snippet) > 100:
                        snippet = snippet[:97] + "..."
                    click.echo(f"    {'':10s} {snippet}")
                click.echo(f"    {'':10s} {r['path']}")
                click.echo()


@cli.command("log")
@click.argument("entity_ref")
@click.option("--author", required=True)
@click.option("--note", required=True)
@click.pass_context
def log_command(ctx: click.Context, entity_ref: str, author: str, note: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = log_activity(root, entity_ref=entity_ref, author=author, note=note)
    _echo_touched(root, [touched])


def main() -> None:
    try:
        cli.main(standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("Aborted!", err=True)
        sys.exit(1)
