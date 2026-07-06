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


def edit_project(
    repo_root: Path,
    *,
    project_slug: str,
    actor: str,
    title: str | None = None,
    goal: str | None = None,
    owners: list[str] | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
) -> Path:
    """Edit editable fields on a project.

    Only provided fields are updated. None means "don't change".
    """
    project_path = project_dir(repo_root, project_slug)
    frontmatter, body = read_entity_user_facing(project_path / "PROJECT.md", label="project")

    changes: list[str] = []

    if title is not None and title.strip():
        old_title = str(frontmatter.get("title", ""))
        frontmatter["title"] = title.strip()
        # Also update the H1 in the body
        import re
        body = re.sub(r"^# .+$", f"# {title.strip()}", body, count=1)
        changes.append(f"Title: {old_title} → {title.strip()}")

    if goal is not None and goal.strip():
        old_goal = str(frontmatter.get("goal", ""))
        frontmatter["goal"] = goal.strip()
        # Also update the ## Goal section in the body
        import re
        body = re.sub(
            r"## Goal\n\n.+",
            f"## Goal\n\n{goal.strip()}",
            body,
            count=1,
        )
        changes.append(f"Goal: {old_goal} → {goal.strip()}")

    if owners is not None:
        old_owners = ", ".join(str(o) for o in frontmatter.get("owners", []))
        frontmatter["owners"] = owners
        changes.append(f"Owners: {old_owners or '(none)'} → {', '.join(owners)}")

    if tags is not None:
        old_tags = ", ".join(str(t) for t in frontmatter.get("tags", []))
        frontmatter["tags"] = tags
        changes.append(f"Tags: {old_tags or '(none)'} → {', '.join(tags)}")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title, --goal, --owners, or --tags")

    action = f"Edited project: {'; '.join(changes)}"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(project_path / "PROJECT.md", frontmatter=frontmatter, body=body)
    return project_path / "PROJECT.md"
