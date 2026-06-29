from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify


def _missing_epic(raw: str) -> TrailmindError:
    return TrailmindError(f"epic {raw} does not exist")


def _resolve_epic(repo_root: Path, raw: str) -> Path:
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
        raise _missing_epic(raw)

    candidate = repo_root / Path(*posix_path.parts)
    try:
        candidate.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise _missing_epic(raw) from exc

    if not (candidate / "EPIC.md").is_file():
        raise _missing_epic(raw)
    return candidate


def _ensure_milestones_directory(milestones_path: Path) -> None:
    if milestones_path.exists() and not milestones_path.is_dir():
        raise TrailmindError(f"milestones path {milestones_path} is not a directory")
    milestones_path.mkdir(parents=True, exist_ok=True)


def _validate_date(raw: str) -> str:
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise TrailmindError("milestone date must be YYYY-MM-DD") from exc
    return raw


def _initial_body(title: str, milestone_date: str) -> str:
    return f"# {title}\n\nDate: {milestone_date}\n"


def add_milestone(repo_root: Path, *, epic: str, title: str, milestone_date: str) -> Path:
    milestone_date = _validate_date(milestone_date)
    epic_path = _resolve_epic(repo_root, epic)
    milestones_path = epic_path / "milestones"
    _ensure_milestones_directory(milestones_path)

    milestone_id = next_entity_id(milestones_path, entity="M")
    milestone_path = milestones_path / f"{milestone_id}-{slugify(title)}.md"
    write_entity(
        milestone_path,
        frontmatter={
            "id": milestone_id,
            "title": title,
            "date": milestone_date,
            "status": "planned",
            "created": date.today().isoformat(),
        },
        body=_initial_body(title, milestone_date),
    )
    return milestone_path
