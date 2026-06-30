from __future__ import annotations

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
from trailmind.issue import add_issue, carry_issue, close_issue, link_issue
from trailmind.log import log_activity
from trailmind.milestone import add_milestone
from trailmind.paths import find_repo_root
from trailmind.project import init_project
from trailmind.roster import Roster
from trailmind.security_scan import scan_paths
from trailmind.serve import serve_repo
from trailmind.task import (
    add_task,
    close_task,
    normalize_task_statuses,
    set_task_status,
    split_csv,
    update_task_status,
)


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
@click.pass_context
def roster_list(ctx: click.Context) -> None:
    root = find_repo_root(_cwd_from_context(ctx))
    roster = Roster.load(root / "roster.yaml")
    for developer in roster.developers:
        click.echo(f"{developer.shortname}\t{developer.email}\t{developer.uid}\t{developer.name}")


@cli.group("project")
def project_group() -> None:
    """Manage projects."""


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
    touched = set_task_status(root, task_ref=task_ref, status=status, actor=actor, note=note)
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


@cli.group("issue")
def issue_group() -> None:
    """Manage issues."""


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


@cli.group("milestone")
def milestone_group() -> None:
    """Manage milestones."""


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
