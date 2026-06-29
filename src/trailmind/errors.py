import click


class TrailmindError(click.ClickException):
    """Base class for user-facing Trailmind errors."""

    def show(self, file=None) -> None:
        if file is None:
            file = click.get_text_stream("stderr")
        click.echo(f"error: {self.format_message()}", file=file)
