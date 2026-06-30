from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.errors import TrailmindError
from trailmind.paths import validate_path_component


def resolve_project_dir(repo_root: Path, raw: str) -> Path:
    try:
        slug = validate_path_component(raw, "project")
    except TrailmindError as exc:
        raise TrailmindError(f"project {raw} does not exist") from exc
    project_path = repo_root / "projects" / slug
    if not (project_path / "PROJECT.md").is_file():
        raise TrailmindError(f"project {raw} does not exist")
    return project_path


def resolve_epic_dir(repo_root: Path, raw: str) -> Path:
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in posix_path.parts
        or ".." in windows_path.parts
        or len(posix_path.parts) != 3
        or posix_path.parts[0] != "projects"
    ):
        raise TrailmindError(f"epic {raw} does not exist")
    epic_path = repo_root / Path(*posix_path.parts)
    try:
        epic_path.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"epic {raw} does not exist") from exc
    if not (epic_path / "EPIC.md").is_file():
        raise TrailmindError(f"epic {raw} does not exist")
    return epic_path


def resolve_project_or_epic_scope(repo_root: Path, *, project: str | None, epic: str | None) -> tuple[Path, str]:
    selected = [value for value in (project, epic) if value]
    if len(selected) != 1:
        raise TrailmindError("exactly one of --project or --epic is required")
    if project:
        return resolve_project_dir(repo_root, project), "project"
    assert epic is not None
    return resolve_epic_dir(repo_root, epic), "epic"


def iter_epic_dirs(repo_root: Path, *, project: str | None = None, epic: str | None = None) -> list[Path]:
    if epic:
        return [resolve_epic_dir(repo_root, epic)]
    projects_root = repo_root / "projects"
    if project:
        project_dirs = [resolve_project_dir(repo_root, project)]
    elif projects_root.exists():
        if not projects_root.is_dir():
            raise TrailmindError(f"projects path {projects_root} is not a directory")
        project_dirs = sorted(path for path in projects_root.iterdir() if (path / "PROJECT.md").is_file())
    else:
        project_dirs = []
    epics: list[Path] = []
    for project_dir in project_dirs:
        epics.extend(sorted(path for path in project_dir.iterdir() if (path / "EPIC.md").is_file()))
    return epics
