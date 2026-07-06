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
from trailmind.inbox import add_inbox_item, list_inbox_items, resolve_inbox_item
from trailmind.issue import (
    ISSUE_SEVERITIES,
    add_issue,
    assign_issue,
    carry_issue,
    close_issue,
    edit_issue,
    link_issue,
    list_issues,
    set_issue_severity,
)
from trailmind.log import log_activity
from trailmind.milestone import add_milestone, list_milestones
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
from trailmind.serve import serve_repo
from trailmind.show import format_entity_show, show_entity
from trailmind.stats import build_stats, format_stats
from trailmind.sweep import build_sweep_report, format_sweep_report, sweep_report_to_dict
from trailmind.task import (
    DEFAULT_PRIORITY,
    TASK_PRIORITIES,
    add_task,
    add_task_deliverable,
    assign_task,
    close_task,
    complete_task,
    complete_task_deliverable,
    edit_task,
    list_tasks,
    normalize_task_statuses,
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
@click.pass_context
def export_command(ctx: click.Context, output: str | None) -> None:
    """Export all project data as JSON."""
    root = find_repo_root(_cwd_from_context(ctx))
    data = export_repo(root)
    rendered = format_export(data)
    if output:
        output_path = root / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        click.echo(output_path.relative_to(root).as_posix())
    else:
        click.echo(rendered)


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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of Markdown.")
@click.pass_context
def inbox_list(ctx: click.Context, project_slug: str | None, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    items = list_inbox_items(root, project=project_slug, epic=epic_ref)
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


@cli.group("task")
def task_group() -> None:
    """Manage tasks."""


@task_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--status", default=None, type=click.Choice(TASK_STATUSES, case_sensitive=False),
              help="Filter by task status.")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--priority", default=None, type=click.Choice(TASK_PRIORITIES, case_sensitive=False),
              help="Filter by priority.")
@click.option("--due-before", default=None, help="Filter tasks due before YYYY-MM-DD.")
@click.option("--due-after", default=None, help="Filter tasks due after YYYY-MM-DD.")
@click.option("--overdue", is_flag=True, help="Show only overdue tasks (not done/wontfix).")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def task_list_cmd(
    ctx: click.Context,
    epic_ref: str | None,
    status: str | None,
    owner: str | None,
    priority: str | None,
    due_before: str | None,
    due_after: str | None,
    overdue: bool,
    json_output: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    tasks = list_tasks(
        root,
        epic_ref=epic_ref,
        status=status,
        owner=owner,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
    )
    if json_output:
        click.echo(json.dumps(tasks, ensure_ascii=False, indent=2))
    else:
        if not tasks:
            click.echo("No tasks.")
            return
        for t in tasks:
            due = t.get("due", "")
            pri = t.get("priority", "")
            extras = f" [{pri}]" if pri else ""
            due_str = f" due:{due}" if due else ""
            click.echo(f"{t['id']:16s} {t['status']:14s} {t['owner']:12s}{extras}{due_str}  {t['title']}")
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
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
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
@click.option("--status", default=None, type=click.Choice(("open", "done", "wontfix"), case_sensitive=False),
              help="Filter by issue status.")
@click.option("--severity", default=None, type=click.Choice(ISSUE_SEVERITIES, case_sensitive=False),
              help="Filter by severity.")
@click.option("--owner", default=None, help="Filter by owner shortname.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def issue_list_cmd(
    ctx: click.Context,
    epic_ref: str | None,
    status: str | None,
    severity: str | None,
    owner: str | None,
    json_output: bool,
) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    issues = list_issues(root, epic_ref=epic_ref, status=status, severity=severity, owner=owner)
    if json_output:
        click.echo(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        if not issues:
            click.echo("No issues.")
            return
        for i in issues:
            sev = f" [{i['severity']}]" if i['severity'] else ""
            owner_str = f" @{i['owner']}" if i.get('owner') else ""
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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def milestone_list_cmd(ctx: click.Context, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    milestones = list_milestones(root, epic_ref=epic_ref)
    if json_output:
        click.echo(json.dumps(milestones, ensure_ascii=False, indent=2))
    else:
        if not milestones:
            click.echo("No milestones.")
            return
        for m in milestones:
            click.echo(f"{m['id']:12s} {m['status']:10s} {m['date']:12s} {m['title']}")
            click.echo(f"{'':12s} {'':10s} {'':12s} {m['path']}")


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
