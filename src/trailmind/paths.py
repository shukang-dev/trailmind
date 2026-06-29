from __future__ import annotations

from pathlib import Path

from trailmind.errors import TrailmindError


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise TrailmindError("not inside a git repository")


def require_managed_repo(start: Path | None = None) -> Path:
    root = find_repo_root(start)
    if not (root / "roster.yaml").exists() and not (root / "projects").exists():
        raise TrailmindError("not inside a Trailmind managed repository")
    return root


def project_dir(repo_root: Path, slug: str) -> Path:
    return repo_root / "projects" / slug


def epic_dir(repo_root: Path, project: str, epic: str) -> Path:
    return repo_root / "projects" / project / epic
