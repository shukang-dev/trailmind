from __future__ import annotations

from datetime import date
from pathlib import Path

from trailmind.agents import render_project_agents
from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.paths import project_dir


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
            "owners": owners,
            "tags": tags,
            "created": date.today().isoformat(),
        },
        body=f"# {title}\n\n## Goal\n\n{goal}\n",
    )
    agents_path.write_text(render_project_agents(slug, title), encoding="utf-8")
    return [project_path, agents_path]
