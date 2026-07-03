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
from trailmind.epic import init_epic
from trailmind.errors import TrailmindError
from trailmind.inbox import add_inbox_item, list_inbox_items, resolve_inbox_item
from trailmind.issue import add_issue, carry_issue, close_issue, link_issue, list_issues
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
from trailmind.project import init_project
from trailmind.roster import Roster
from trailmind.security_scan import scan_paths
from trailmind.serve import serve_repo
from trailmind.sweep import build_sweep_report, format_sweep_report, sweep_report_to_dict
from trailmind.task import (
    DEFAULT_PRIORITY,
    TASK_PRIORITIES,
    add_task,
    add_task_deliverable,
    close_task,
    complete_task_deliverable,
    list_tasks,
    normalize_task_statuses,
    set_task_due,
    set_task_priority,
    set_task_status,
    split_csv,
    update_task_status,
)
from trailmind.task_rules import linked_open_issues_for_task


@click.group()
@click.version_option(__version__, prog_name="trailmind")
def cli() -> None:
    """Trailmind: Markdown-backed project tracking and AI agent handoff."""


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


@cli.group("task")
def task_group() -> None:
    """Manage tasks."""


@task_group.command("list")
@click.option("--epic", "epic_ref", default=None)
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def task_list_cmd(ctx: click.Context, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    tasks = list_tasks(root, epic_ref=epic_ref)
    if json_output:
        click.echo(json.dumps(tasks, ensure_ascii=False, indent=2))
    else:
        if not tasks:
            click.echo("No tasks.")
            return
        for t in tasks:
            click.echo(f"{t['id']:16s} {t['status']:14s} {t['owner']:12s} {t['title']}")
            click.echo(f"{'':16s} {'':14s} {'':12s} {t['path']}")


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
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON instead of tabular output.")
@click.pass_context
def issue_list_cmd(ctx: click.Context, epic_ref: str | None, json_output: bool) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    issues = list_issues(root, epic_ref=epic_ref)
    if json_output:
        click.echo(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        if not issues:
            click.echo("No issues.")
            return
        for i in issues:
            sev = f" [{i['severity']}]" if i['severity'] else ""
            click.echo(f"{i['id']:16s} {i['status']:10s}{sev} {i['title']}")
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
