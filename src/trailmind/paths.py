from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

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


def validate_path_component(value: str, label: str) -> str:
    windows_path = PureWindowsPath(value)
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise TrailmindError(f"{label} must be a single safe relative path component")
    return value


def project_dir(repo_root: Path, slug: str) -> Path:
    return repo_root / "projects" / validate_path_component(slug, "project slug")


def epic_dir(repo_root: Path, project: str, epic: str) -> Path:
    project_slug = validate_path_component(project, "project slug")
    epic_slug = validate_path_component(epic, "epic slug")
    return repo_root / "projects" / project_slug / epic_slug
