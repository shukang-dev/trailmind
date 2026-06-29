import click


class TrailmindError(click.ClickException):
    """Base class for user-facing Trailmind errors."""

    def show(self, file=None) -> None:
        click.echo(f"error: {self.format_message()}", file=file)
