from __future__ import annotations

from importlib.resources import files

from jinja2 import Environment, FileSystemLoader


def _environment() -> Environment:
    template_dir = files("trailmind").joinpath("templates")
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
        keep_trailing_newline=True,
    )


def render_project_agents(project_slug: str, title: str) -> str:
    template = _environment().get_template("agents-project.md.j2")
    return template.render(project_slug=project_slug, title=title)


def render_epic_agents(project_slug: str, epic_slug: str, title: str) -> str:
    template = _environment().get_template("agents-epic.md.j2")
    return template.render(project_slug=project_slug, epic_slug=epic_slug, title=title)
