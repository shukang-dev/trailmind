from __future__ import annotations

from datetime import date
from pathlib import Path

from trailmind.agents import render_project_agents
from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.paths import project_dir


PROJECT_STATES = ("planning", "active", "paused", "completed", "archived", "cancelled")
DEFAULT_PROJECT_STATE = "active"


def validate_project_state(state: str) -> str:
    normalized = state.strip().lower()
    if normalized not in PROJECT_STATES:
        expected = ", ".join(PROJECT_STATES)
        raise TrailmindError(f"invalid project state {state!r}; expected one of: {expected}")
    return normalized


def set_project_status(
    repo_root: Path,
    *,
    project_slug: str,
    state: str,
    actor: str,
    note: str | None = None,
) -> Path:
    validated = validate_project_state(state)
    project_path = project_dir(repo_root, project_slug)
    frontmatter, body = read_entity_user_facing(project_path / "PROJECT.md", label="project")
    old_state = str(frontmatter.get("state", DEFAULT_PROJECT_STATE))
    frontmatter["state"] = validated
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"State changed from {old_state} to {validated}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(project_path / "PROJECT.md", frontmatter=frontmatter, body=body)
    return project_path / "PROJECT.md"


def init_project(
    repo_root: Path,
    *,
    slug: str,
    title: str,
    goal: str,
    owners: list[str],
    tags: list[str],
) -> list[Path]:
    path = project_dir(repo_root, slug)
    if path.exists():
        raise TrailmindError(f"project {slug} already exists")
    path.mkdir(parents=True, exist_ok=False)

    project_path = path / "PROJECT.md"
    agents_path = path / "AGENTS.md"
    write_entity(
        project_path,
        frontmatter={
            "slug": slug,
            "title": title,
            "goal": goal,
            "state": DEFAULT_PROJECT_STATE,
            "owners": owners,
            "tags": tags,
            "created": date.today().isoformat(),
        },
        body=f"# {title}\n\n## Goal\n\n{goal}\n",
    )
    agents_path.write_text(render_project_agents(slug, title), encoding="utf-8")
    return [project_path, agents_path]
