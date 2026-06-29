from __future__ import annotations

from datetime import date
from pathlib import Path

from trailmind.agents import render_epic_agents
from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.paths import epic_dir, project_dir


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
            "state": "active",
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
