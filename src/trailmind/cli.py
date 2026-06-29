from __future__ import annotations

import sys
from pathlib import Path

import click

from trailmind import __version__
from trailmind.epic import init_epic
from trailmind.errors import TrailmindError
from trailmind.paths import find_repo_root
from trailmind.project import init_project
from trailmind.roster import Roster


@click.group()
@click.version_option(__version__, prog_name="trailmind")
def cli() -> None:
    """Trailmind: Markdown-backed project tracking and AI agent handoff."""


@cli.command("status")
def status_command() -> None:
    raise TrailmindError("not inside a Trailmind managed repository")


def _cwd_from_context(ctx: click.Context) -> Path:
    if ctx.obj and "cwd" in ctx.obj:
        return Path(ctx.obj["cwd"])
    return Path.cwd()


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _echo_touched(repo_root: Path, paths: list[Path]) -> None:
    for path in paths:
        click.echo(path.relative_to(repo_root).as_posix())


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


def main() -> None:
    try:
        cli.main(standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("Aborted!", err=True)
        sys.exit(1)
