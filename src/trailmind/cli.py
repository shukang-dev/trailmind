from __future__ import annotations

import sys

import click

from trailmind import __version__
from trailmind.errors import TrailmindError


@click.group()
@click.version_option(__version__, prog_name="trailmind")
def cli() -> None:
    """Trailmind: Markdown-backed project tracking and AI agent handoff."""


@cli.command("status")
def status_command() -> None:
    raise TrailmindError("not inside a Trailmind managed repository")


def main() -> None:
    try:
        cli.main(standalone_mode=False)
    except TrailmindError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("Aborted!", err=True)
        sys.exit(1)
