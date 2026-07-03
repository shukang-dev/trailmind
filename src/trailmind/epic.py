from __future__ import annotations

from datetime import date
from pathlib import Path

from trailmind.agents import render_epic_agents
from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.paths import epic_dir, project_dir
from trailmind.scopes import resolve_epic_dir


EPIC_STATES = ("planning", "active", "paused", "completed", "archived", "cancelled")
DEFAULT_EPIC_STATE = "active"


def validate_epic_state(state: str) -> str:
    normalized = state.strip().lower()
    if normalized not in EPIC_STATES:
        expected = ", ".join(EPIC_STATES)
        raise TrailmindError(f"invalid epic state {state!r}; expected one of: {expected}")
    return normalized


def set_epic_status(
    repo_root: Path,
    *,
    epic_ref: str,
    state: str,
    actor: str,
    note: str | None = None,
) -> Path:
    validated = validate_epic_state(state)
    epic_path = resolve_epic_dir(repo_root, epic_ref)
    frontmatter, body = read_entity_user_facing(epic_path / "EPIC.md", label="epic")
    old_state = str(frontmatter.get("state", DEFAULT_EPIC_STATE))
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
    write_entity(epic_path / "EPIC.md", frontmatter=frontmatter, body=body)
    return epic_path / "EPIC.md"


def init_epic(
    repo_root: Path,
    *,
    project: str,
    slug: str,
    title: str,
    goal: str,
    start: str,
    target: str,
    roster: list[str],
    repos: list[str],
) -> list[Path]:
    project_path = project_dir(repo_root, project)
    if not (project_path / "PROJECT.md").exists():
        raise TrailmindError(f"project {project} does not exist")

    path = epic_dir(repo_root, project, slug)
    if path.exists():
        raise TrailmindError(f"epic {project}/{slug} already exists")
    path.mkdir(parents=True, exist_ok=False)

    dirs = [
        path / "tasks",
        path / "issues",
        path / "milestones",
        path / "docs" / "specs",
        path / "docs" / "plans",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=False)

    epic_path = path / "EPIC.md"
    agents_path = path / "AGENTS.md"
    write_entity(
        epic_path,
        frontmatter={
            "slug": slug,
            "title": title,
            "project": project,
            "goal": goal,
            "state": DEFAULT_EPIC_STATE,
            "start": start,
            "target": target,
            "roster": roster,
            "repos": repos,
            "carried_issues": [],
            "created": date.today().isoformat(),
        },
        body=f"# {title}\n\n## Goal\n\n{goal}\n",
    )
    agents_path.write_text(render_epic_agents(project, slug, title), encoding="utf-8")
    return [epic_path, agents_path, *dirs]
