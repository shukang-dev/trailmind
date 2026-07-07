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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of text report.")
@click.pass_context
def stats_command(ctx: click.Context, json_output: bool) -> None:
    """Show repository statistics."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = build_stats(root)
    if json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_stats(data), nl=False)


@cli.command("tree")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def tree_command(ctx: click.Context, json_output: bool) -> None:
    """Show project structure as a tree with entity counts."""
    root = find_repo_root(_cwd_from_context(ctx))
    tree = build_tree(root)
    if json_output:
        click.echo(json.dumps(tree, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(format_tree(tree))


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


@cli.command("export")
@click.option("--output", "-o", default=None, help="Write to file instead of stdout.")
@click.option("--format", "fmt", default="json", type=click.Choice(("json", "csv"), case_sensitive=False),
              help="Output format (default: json). CSV outputs tasks and issues as separate CSV blocks.")
@click.pass_context
def export_command(ctx: click.Context, output: str | None, fmt: str) -> None:
    """Export all project data as JSON or CSV."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = export_repo(root)

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
@click.pass_context
def inbox_add(
    ctx: click.Context,
    project_slug: str | None,
    epic_ref: str | None,
    author: str,
    title: str,
    note: str,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = add_inbox_item(root, project=project_slug, epic=epic_ref, author=author, title=title, note=note)
    _echo_touched(root, [touched])


@inbox_group.command("list")
@click.option("--project", "project_slug", default=None)
@click.option("--epic", "epic_ref", default=None)
@click.option("--status", default=None, type=click.Choice(("open", "resolved"), case_sensitive=False),
              help="Filter by inbox item status.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.pass_context
def inbox_list(ctx: click.Context, project_slug: str | None, epic_ref: str | None,
               status: str | None, limit: int | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    items = list_inbox_items(root, project=project_slug, epic=epic_ref, status=status)
    if limit:
        items = items[:limit]
    if json_output:
        data = [
            {
                "item_id": item.item_id,
                "title": item.title,
                "status": item.status,
                "path": item.path.relative_to(root).as_posix(),
            }
            for item in items
        ]
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not items:
            click.echo("No inbox items.")
            return
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
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def spec_list(ctx: click.Context, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    specs = list_specs(root, epic_ref=epic_ref)
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
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def plan_list_cmd(ctx: click.Context, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    plans = list_plans(root, epic_ref=epic_ref)
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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def project_list_cmd(ctx: click.Context, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    projects_path = root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        if json_output:
            click.echo("[]")
        else:
            click.echo("No projects.")
        return
    from trailmind.log import read_entity_user_facing

    projects = []
    for project_path in sorted(p for p in projects_path.iterdir() if (p / "PROJECT.md").is_file()):
        try:
            fm, _body = read_entity_user_facing(project_path / "PROJECT.md", label="project")
            projects.append({
                "slug": str(fm.get("slug") or project_path.name),
                "title": str(fm.get("title") or project_path.name),
                "goal": str(fm.get("goal") or ""),
                "state": str(fm.get("state") or "unknown"),
                "path": project_path.relative_to(root).as_posix(),
            })
        except TrailmindError:
            continue
    if json_output:
        click.echo(json.dumps(projects, ensure_ascii=False, indent=2))
    else:
        for p in projects:
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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def epic_list_cmd(ctx: click.Context, project_slug: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    from trailmind.log import read_entity_user_facing

    epics = []
    projects_path = root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        if json_output:
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
                epics.append({
                    "project": project_dir.name,
                    "slug": str(fm.get("slug") or epic_dir.name),
                    "title": str(fm.get("title") or epic_dir.name),
                    "goal": str(fm.get("goal") or ""),
                    "state": str(fm.get("state") or "unknown"),
                    "target": str(fm.get("target") or ""),
                    "path": epic_dir.relative_to(root).as_posix(),
                })
            except TrailmindError:
                continue
    if json_output:
        click.echo(json.dumps(epics, ensure_ascii=False, indent=2))
    else:
        for e in epics:
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
@click.option("--has-due", "has_due", flag_value=True, default=None,
              help="Show only tasks that have a due date.")
@click.option("--no-due", "has_due", flag_value=False,
              help="Show only tasks without a due date.")
@click.option("--tag", default=None, help="Filter by tag (case-insensitive substring match).")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "priority", "due", "status", "title"), case_sensitive=False),
              help="Sort tasks (default: created).")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "owner", "priority"), case_sensitive=False),
              help="Group tasks by status, owner, or priority.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
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
    has_due: bool | None,
    tag: str | None,
    sort_by: str,
    group_by: str | None,
    compact: bool,
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
        groups: dict[str, list[dict]] = defaultdict(list)
        for t in tasks:
            key = t.get(group_by, "") or "unassigned"
            groups[key].append(t)

        # Sort groups: by natural order for status/priority, alphabetical for owner
        if group_by == "status":
            order = {s: i for i, s in enumerate(TASK_STATUSES)}
            sorted_keys = sorted(groups.keys(), key=lambda k: order.get(k, 99))
        elif group_by == "priority":
            from trailmind.task import PRIORITY_ORDER
            sorted_keys = sorted(groups.keys(), key=lambda k: PRIORITY_ORDER.get(k, 99))
        else:
            sorted_keys = sorted(groups.keys())

        for key in sorted_keys:
            group_tasks = groups[key]
            click.echo(f"\n{key.upper()} ({len(group_tasks)})")
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
@click.option("--tags", default=None, help="Comma-separated tags.")
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
    tags: str | None,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    tag_list = split_csv(tags) if tags else []
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
        tags=tag_list,
    )
    _echo_touched(root, [touched])


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
@click.pass_context
def task_set_status(
    ctx: click.Context,
    task_ref: str,
    status: str,
    actor: str,
    note: str | None,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched, warning = set_task_status(root, task_ref=task_ref, status=status, actor=actor, note=note)
    _echo_touched(root, [touched])
    if warning:
        click.echo(warning)


@task_group.command("set-priority")
@click.argument("task_ref")
@click.argument("priority", type=click.Choice(TASK_PRIORITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_set_priority(
    ctx: click.Context,
    task_ref: str,
    priority: str,
    actor: str,
    note: str | None,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_task_priority(root, task_ref=task_ref, priority=priority, actor=actor, note=note)
    _echo_touched(root, [touched])


@task_group.command("due")
@click.argument("task_ref")
@click.argument("due_date", required=False, default=None)
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.option("--clear", is_flag=True, help="Clear the due date.")
@click.pass_context
def task_due(
    ctx: click.Context,
    task_ref: str,
    due_date: str | None,
    actor: str,
    note: str | None,
    clear: bool,
) -> None:
    """Set or clear a task due date (YYYY-MM-DD)."""
    root = find_repo_root(_cwd_from_context(ctx))
    if clear:
        touched = set_task_due(root, task_ref=task_ref, due_date=None, actor=actor, note=note)
    else:
        if due_date is None:
            raise TrailmindError("due date is required (or use --clear)")
        touched = set_task_due(root, task_ref=task_ref, due_date=due_date, actor=actor, note=note)
    _echo_touched(root, [touched])


@task_group.command("assign")
@click.argument("task_ref")
@click.argument("owner")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_assign(
    ctx: click.Context,
    task_ref: str,
    owner: str,
    actor: str,
    note: str | None,
) -> None:
    """Reassign a task to a different owner."""
    root = find_repo_root(_cwd_from_context(ctx))
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
@click.option("--limit", default=10, show_default=True, type=click.IntRange(min=1, max=50),
              help="Maximum tasks to show.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def task_next(ctx: click.Context, owner: str | None, epic_ref: str | None, project_ref: str | None,
              limit: int, json_output: bool) -> None:
    """Show the most actionable tasks next to work on (sorted by priority then due date)."""
    root = find_repo_root(_cwd_from_context(ctx))
    tasks = next_tasks(root, owner=owner, epic=epic_ref, project=project_ref, limit=limit)

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


@task_group.command("edit")
@click.argument("task_ref")
@click.option("--title", default=None, help="New task title.")
@click.option("--code-paths", default=None, help="Comma-separated code paths.")
@click.option("--design-doc", default=None, help="Path to design document.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_edit(
    ctx: click.Context,
    task_ref: str,
    title: str | None,
    code_paths: str | None,
    design_doc: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on a task."""
    root = find_repo_root(_cwd_from_context(ctx))
    paths = split_csv(code_paths) if code_paths is not None else None
    touched = edit_task(
        root,
        task_ref=task_ref,
        actor=actor,
        title=title,
        code_paths=paths,
        design_doc=design_doc,
        note=note,
    )
    _echo_touched(root, [touched])


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
@click.argument("task_refs", nargs=-1, required=True)
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def task_bulk_status(
    ctx: click.Context,
    task_refs: tuple[str, ...],
    status: str,
    actor: str,
    note: str | None,
) -> None:
    """Bulk-update task status for multiple tasks (e.g. T-001 T-002 T-003 ready)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = []
    for task_ref in task_refs:
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


@cli.group("issue")
def issue_group() -> None:
    """Manage issues."""


@issue_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--project", "project_ref", default=None, help="Filter by project slug.")
@click.option("--status", default=None, type=click.Choice(("open", "done", "wontfix"), case_sensitive=False),
              help="Filter by issue status.")
@click.option("--severity", default=None, type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False),
              help="Filter by severity.")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--sort", "sort_by", default="created",
              type=click.Choice(("created", "severity", "status", "title"), case_sensitive=False),
              help="Sort issues (default: created).")
@click.option("--group-by", default=None,
              type=click.Choice(("status", "severity", "owner"), case_sensitive=False),
              help="Group issues by status, severity, or owner.")
@click.option("--compact", is_flag=True, help="Compact single-line output.")
@click.option("--csv", "csv_output", is_flag=True, help="Output as CSV for spreadsheet import.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def issue_list_cmd(
    ctx: click.Context,
    epic_ref: str | None,
    project_ref: str | None,
    status: str | None,
    severity: str | None,
    owner: str | None,
    sort_by: str,
    group_by: str | None,
    compact: bool,
    csv_output: bool,
    limit: int | None,
    json_output: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    issues = list_issues(root, epic_ref=epic_ref, project_ref=project_ref,
                          status=status, severity=severity, owner=owner, sort_by=sort_by)
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
            click.echo(f"\n{key.upper()} ({len(group_issues)})")
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
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--severity", required=True)
@click.pass_context
def issue_add(
    ctx: click.Context,
    epic: str,
    filer: str,
    title: str,
    description: str,
    severity: str,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    touched = add_issue(root, epic=epic, filer=filer, title=title, description=description, severity=severity)
    _echo_touched(root, [touched])


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
@click.pass_context
def issue_assign(
    ctx: click.Context,
    issue_ref: str,
    owner: str,
    actor: str,
    note: str | None,
) -> None:
    """Reassign an issue to a different owner."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = assign_issue(root, issue_ref=issue_ref, owner=owner, actor=actor, note=note)
    _echo_touched(root, [touched])


@issue_group.command("set-severity")
@click.argument("issue_ref")
@click.argument("severity", type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False))
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_set_severity(
    ctx: click.Context,
    issue_ref: str,
    severity: str,
    actor: str,
    note: str | None,
) -> None:
    """Change an issue's severity."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_issue_severity(root, issue_ref=issue_ref, severity=severity, actor=actor, note=note)
    _echo_touched(root, [touched])


@issue_group.command("edit")
@click.argument("issue_ref")
@click.option("--title", default=None, help="New issue title.")
@click.option("--description", default=None, help="New issue description.")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def issue_edit(
    ctx: click.Context,
    issue_ref: str,
    title: str | None,
    description: str | None,
    actor: str,
    note: str | None,
) -> None:
    """Edit editable fields on an issue."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = edit_issue(
        root,
        issue_ref=issue_ref,
        actor=actor,
        title=title,
        description=description,
        note=note,
    )
    _echo_touched(root, [touched])


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
@click.option("--sort", "sort_by", default="date",
              type=click.Choice(("date", "created", "status", "title"), case_sensitive=False),
              help="Sort milestones (default: date).")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Limit number of results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def milestone_list_cmd(ctx: click.Context, epic_ref: str | None, project_ref: str | None,
                        status: str | None, sort_by: str, limit: int | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    milestones = list_milestones(root, epic_ref=epic_ref, project_ref=project_ref,
                                  status=status, sort_by=sort_by)
    if limit:
        milestones = milestones[:limit]
    if json_output:
        click.echo(json.dumps(milestones, ensure_ascii=False, indent=2))
    else:
        if not milestones:
            click.echo("No milestones.")
            return
        for m in milestones:
            click.echo(f"{m['id']:12s} {m['status']:12s} {m['date']:12s} {m['title']}")
            click.echo(f"{'':12s} {'':12s} {'':12s} {m['path']}")


@milestone_group.command("set-status")
@click.argument("milestone_ref")
@click.argument("status")
@click.option("--actor", required=True)
@click.option("--note", default=None)
@click.pass_context
def milestone_set_status(ctx: click.Context, milestone_ref: str, status: str, actor: str, note: str | None) -> None:
    """Change a milestone's status (planned, in_progress, done)."""
    root = find_repo_root(_cwd_from_context(ctx))
    touched = set_milestone_status(root, milestone_ref=milestone_ref, status=status, actor=actor, note=note)
    _echo_touched(root, [touched])


@milestone_group.command("add")
@click.option("--epic", required=True)
@click.option("--title", required=True)
@click.option("--date", "milestone_date", required=True)
@click.pass_context
def milestone_add(ctx: click.Context, epic: str, title: str, milestone_date: str) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def activity_command(
    ctx: click.Context,
    limit: int,
    entity_type: str | None,
    actor: str | None,
    since: str | None,
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
    )

    if json_output:
        click.echo(json.dumps(entries, ensure_ascii=False, indent=2))
        return

    if not entries:
        click.echo("No activity found.")
        return

    for e in entries:
        type_icon = {
            "project": "📦", "epic": "🎯", "task": "✅", "issue": "🐛",
            "milestone": "🏁", "inbox": "📥", "spec": "📐", "plan": "📋",
        }.get(e["entity_type"], "📄")
        note_str = f" — {e['note']}" if e["note"] else ""
        click.echo(f"  {e['date']}  {type_icon} {e['action']}")
        click.echo(f"          by {e['actor']} on {e['entity_type']} {e['entity_id']} {e['entity_title']}{note_str}")
        click.echo()


@cli.command("search")
@click.argument("query")
@click.option("--type", "entity_types", default=None,
              help="Filter by entity type (comma-separated: task,issue,epic,project,milestone,inbox,spec,plan).")
@click.option("--limit", default=30, show_default=True, type=click.IntRange(min=1, max=200),
              help="Maximum results.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.pass_context
def search_command(
    ctx: click.Context,
    query: str,
    entity_types: str | None,
    limit: int,
    json_output: bool,
) -> None:
    """Search across all entities by keyword."""
    root = find_repo_root(_cwd_from_context(ctx))
    type_list = [t.strip().lower() for t in entity_types.split(",")] if entity_types else None
    results = search_entities(root, query=query, entity_types=type_list, limit=limit)

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

    click.echo(f"Found {len(results)} result(s) for {query!r}:\n")
    for r in results:
        icon = type_icons.get(r["entity_type"], "📄")
        status_str = f" [{r['status']}]" if r["status"] else ""
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
