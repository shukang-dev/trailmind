from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import next_entity_id, slugify
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing


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


def list_milestones(
    repo_root: Path,
    *,
    epic_ref: str | None = None,
    project_ref: str | None = None,
    status: str | None = None,
    sort_by: str = "date",
) -> list[dict[str, str]]:
    """List milestones in an epic, a project, or across the repo.

    sort_by: "date" (default), "created", "status", "title"
    """
    if epic_ref:
        epic_path = _resolve_epic(repo_root, epic_ref)
        milestone_paths = sorted(epic_path.glob("milestones/M-*.md"))
    elif project_ref:
        proj_dir = repo_root / "projects" / project_ref
        if not proj_dir.exists():
            from trailmind.errors import TrailmindError
            raise TrailmindError(f"project not found: {project_ref}")
        milestone_paths = sorted(proj_dir.glob("*/milestones/M-*.md"))
    else:
        projects_path = repo_root / "projects"
        if not projects_path.exists() or not projects_path.is_dir():
            return []
        milestone_paths = sorted(projects_path.glob("*/*/milestones/M-*.md"))

    milestones = []
    for path in milestone_paths:
        if not path.is_file():
            continue
        try:
            frontmatter, _body = read_entity_user_facing(path, label="milestone")
            rel = path.relative_to(repo_root).as_posix()
            parts = rel.split("/")
            epic = f"projects/{parts[1]}/{parts[2]}" if len(parts) > 2 else ""
            ms = {
                "id": str(frontmatter.get("id") or path.stem),
                "title": str(frontmatter.get("title") or path.stem),
                "status": str(frontmatter.get("status") or "created"),
                "date": str(frontmatter.get("date") or ""),
                "created": str(frontmatter.get("created") or ""),
                "epic": epic,
                "path": rel,
            }
            if status and ms["status"] != status:
                continue
            milestones.append(ms)
        except TrailmindError:
            continue

    # Sort
    STATUS_ORDER = {"in_progress": 0, "planned": 1, "done": 2, "": 3}
    if sort_by == "status":
        milestones.sort(key=lambda m: (STATUS_ORDER.get(m["status"], 3), m.get("date", "")))
    elif sort_by == "title":
        milestones.sort(key=lambda m: m.get("title", "").lower())
    elif sort_by == "created":
        milestones.sort(key=lambda m: m.get("created", ""), reverse=True)
    else:  # date
        milestones.sort(key=lambda m: m.get("date", "9999-99-99"))

    return milestones


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


MILESTONE_STATUSES = ("planned", "in_progress", "done", "cancelled")


def edit_milestone(
    repo_root: Path,
    *,
    milestone_ref: str,
    actor: str,
    title: str | None = None,
    milestone_date: str | None = None,
    status: str | None = None,
    note: str | None = None,
) -> Path:
    """Edit editable fields on a milestone."""
    from trailmind.resolver import resolve_entity
    milestone_path = resolve_entity(repo_root, raw=milestone_ref, entity="M")
    frontmatter, body = read_entity_user_facing(milestone_path, label="milestone")

    changes: list[str] = []

    if title is not None and title.strip():
        old_title = str(frontmatter.get("title", ""))
        frontmatter["title"] = title.strip()
        import re
        body = re.sub(r"^# .+$", f"# {title.strip()}", body, count=1)
        changes.append(f"Title: {old_title} → {title.strip()}")

    if milestone_date is not None:
        validated = _validate_date(milestone_date)
        old_date = str(frontmatter.get("date", ""))
        frontmatter["date"] = validated
        import re
        body = re.sub(r"^Date: .+$", f"Date: {validated}", body, count=1, flags=re.MULTILINE)
        changes.append(f"Date: {old_date} → {validated}")

    if status is not None:
        normalized = status.strip().lower()
        if normalized not in MILESTONE_STATUSES:
            raise TrailmindError(f"invalid milestone status {status!r}; expected one of: {', '.join(MILESTONE_STATUSES)}")
        old_status = str(frontmatter.get("status", "planned"))
        frontmatter["status"] = normalized
        changes.append(f"Status: {old_status} → {normalized}")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title, --date, or --status")

    action = f"Edited milestone: {'; '.join(changes)}"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(milestone_path, frontmatter=frontmatter, body=body)
    return milestone_path


def set_milestone_status(
    repo_root: Path,
    *,
    milestone_ref: str,
    status: str,
    actor: str,
    note: str | None = None,
) -> Path:
    """Change a milestone's status."""
    from trailmind.resolver import resolve_entity

    normalized = status.strip().lower()
    if normalized not in MILESTONE_STATUSES:
        raise TrailmindError(f"invalid milestone status {status!r}; expected one of: {', '.join(MILESTONE_STATUSES)}")

    milestone_path = resolve_entity(repo_root, raw=milestone_ref, entity="M")
    frontmatter, body = read_entity_user_facing(milestone_path, label="milestone")
    old_status = str(frontmatter.get("status", "planned"))

    if old_status == normalized:
        raise TrailmindError(f"milestone is already in {normalized!r} status")

    frontmatter["status"] = normalized
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=f"Status changed from {old_status} to {normalized}",
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(milestone_path, frontmatter=frontmatter, body=body)
    return milestone_path
