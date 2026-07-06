from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.ids import slugify
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.scopes import resolve_project_or_epic_scope


INBOX_STEM_RE = re.compile(r"^(?P<item_id>IN-(?P<day>\d{8})-(?P<sequence>\d{3,}))(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$")


@dataclass(frozen=True)
class InboxItem:
    path: Path
    item_id: str
    title: str
    status: str


def _parse_inbox_stem(stem: str) -> re.Match[str] | None:
    return INBOX_STEM_RE.fullmatch(stem)


def _next_inbox_id(inbox_path: Path) -> str:
    today = date.today().strftime("%Y%m%d")
    max_sequence = 0
    for path in inbox_path.glob(f"IN-{today}-*.md"):
        match = _parse_inbox_stem(path.stem)
        if match is None or match.group("day") != today:
            continue
        max_sequence = max(max_sequence, int(match.group("sequence")))
    return f"IN-{today}-{max_sequence + 1:03d}"


def _iter_inbox_files(repo_root: Path) -> list[Path]:
    projects_path = repo_root / "projects"
    if not projects_path.exists():
        return []
    return sorted(path for path in projects_path.glob("**/inbox/IN-*.md") if path.is_file())


def _is_path_like(raw: str) -> bool:
    windows_path = PureWindowsPath(raw)
    return (
        raw in {".", ".."}
        or "/" in raw
        or "\\" in raw
        or raw.endswith(".md")
        or PurePosixPath(raw).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    )


def _has_parent_reference(raw: str) -> bool:
    return ".." in PurePosixPath(raw).parts or ".." in PureWindowsPath(raw).parts


def _resolve_direct_inbox_path(repo_root: Path, raw: str) -> Path:
    windows_path = PureWindowsPath(raw)
    raw_parts = PurePosixPath(raw).parts
    if (
        PurePosixPath(raw).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or "\\" in raw
        or _has_parent_reference(raw)
        or len(raw_parts) not in {4, 5}
        or raw_parts[0] != "projects"
        or raw_parts[-2] != "inbox"
    ):
        raise TrailmindError(f"inbox item {raw!r} not found")

    candidate = repo_root / raw
    try:
        candidate.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"inbox item {raw!r} not found") from exc

    scope_path = candidate.parents[1]
    marker = "PROJECT.md" if len(raw_parts) == 4 else "EPIC.md"
    if (
        candidate.suffix != ".md"
        or not (scope_path / marker).is_file()
        or _parse_inbox_stem(candidate.stem) is None
        or not candidate.is_file()
    ):
        raise TrailmindError(f"inbox item {raw!r} not found")
    return candidate


def _matches_inbox_ref(path: Path, raw: str) -> bool:
    match = _parse_inbox_stem(path.stem)
    if match is None:
        return False
    return path.stem == raw or match.group("item_id") == raw


def _resolve_inbox_item(repo_root: Path, raw: str) -> Path:
    if _is_path_like(raw):
        return _resolve_direct_inbox_path(repo_root, raw)
    matches = [path for path in _iter_inbox_files(repo_root) if _matches_inbox_ref(path, raw)]
    if not matches:
        raise TrailmindError(f"inbox item {raw!r} not found")
    if len(matches) > 1:
        candidates = ", ".join(path.relative_to(repo_root).as_posix() for path in matches)
        raise TrailmindError(f"inbox item {raw!r} is ambiguous; candidates: {candidates}")
    return matches[0]


def add_inbox_item(
    repo_root: Path,
    *,
    project: str | None,
    epic: str | None,
    author: str,
    title: str,
    note: str,
) -> Path:
    scope_path, scope = resolve_project_or_epic_scope(repo_root, project=project, epic=epic)
    inbox_path = scope_path / "inbox"
    if inbox_path.exists() and not inbox_path.is_dir():
        raise TrailmindError(f"inbox path {inbox_path} is not a directory")
    inbox_path.mkdir(parents=True, exist_ok=True)
    item_id = _next_inbox_id(inbox_path)
    item_path = inbox_path / f"{item_id}-{slugify(title)}.md"
    if item_path.exists():
        raise TrailmindError(f"inbox item {item_path} already exists")
    body = (
        f"# {title}\n\n"
        "## Note\n\n"
        f"{note}\n\n"
        "## Activity Log\n\n"
        f"{action_activity_entry(action='Captured', actor_label='author', actor=author)}\n"
    )
    write_entity(
        item_path,
        frontmatter={
            "id": item_id,
            "title": title,
            "author": author,
            "scope": scope,
            "status": "open",
            "created": date.today().isoformat(),
            "resolved": None,
        },
        body=body,
    )
    return item_path


def list_inbox_items(repo_root: Path, *, project: str | None, epic: str | None) -> list[InboxItem]:
    scope_path, _scope = resolve_project_or_epic_scope(repo_root, project=project, epic=epic)
    inbox_path = scope_path / "inbox"
    if not inbox_path.exists():
        return []
    if not inbox_path.is_dir():
        raise TrailmindError(f"inbox path {inbox_path} is not a directory")
    items: list[InboxItem] = []
    for path in sorted(inbox_path.glob("IN-*.md")):
        frontmatter, _body = read_entity_user_facing(path, label="inbox")
        items.append(
            InboxItem(
                path=path,
                item_id=str(frontmatter.get("id") or path.stem),
                title=str(frontmatter.get("title") or path.stem),
                status=str(frontmatter.get("status") or "open"),
            )
        )
    return items


def open_inbox_items_under(scope_path: Path) -> list[InboxItem]:
    inbox_path = scope_path / "inbox"
    if not inbox_path.exists():
        return []
    if not inbox_path.is_dir():
        raise TrailmindError(f"inbox path {inbox_path} is not a directory")
    items: list[InboxItem] = []
    for path in sorted(inbox_path.glob("IN-*.md")):
        frontmatter, _body = read_entity_user_facing(path, label="inbox")
        status = str(frontmatter.get("status") or "open")
        if status != "open":
            continue
        items.append(
            InboxItem(
                path=path,
                item_id=str(frontmatter.get("id") or path.stem),
                title=str(frontmatter.get("title") or path.stem),
                status=status,
            )
        )
    return items


def resolve_inbox_item(repo_root: Path, *, item_ref: str, resolver: str, note: str) -> Path:
    item_path = _resolve_inbox_item(repo_root, item_ref)
    frontmatter, body = read_entity_user_facing(item_path, label="inbox")
    item_id = str(frontmatter.get("id") or item_path.stem)
    if str(frontmatter.get("status") or "open") != "open":
        raise TrailmindError(f"inbox item {item_id} is not open")
    frontmatter["status"] = "resolved"
    frontmatter["resolved"] = date.today().isoformat()
    body = append_activity_entry(
        body,
        action_activity_entry(action="Resolved", actor_label="resolver", actor=resolver, note=note),
    )
    write_entity(item_path, frontmatter=frontmatter, body=body)
    return item_path


def edit_inbox_item(
    repo_root: Path,
    *,
    item_ref: str,
    actor: str,
    title: str | None = None,
    note: str | None = None,
) -> Path:
    """Edit editable fields on an inbox item."""
    item_path = _resolve_inbox_item(repo_root, item_ref)
    frontmatter, body = read_entity_user_facing(item_path, label="inbox")

    changes: list[str] = []

    if title is not None and title.strip():
        old_title = str(frontmatter.get("title", ""))
        frontmatter["title"] = title.strip()
        import re
        body = re.sub(r"^# .+$", f"# {title.strip()}", body, count=1)
        changes.append(f"Title: {old_title} → {title.strip()}")

    if not changes:
        raise TrailmindError("no fields to edit; provide --title")

    action = f"Edited inbox item: {'; '.join(changes)}"
    body = append_activity_entry(
        body,
        action_activity_entry(
            action=action,
            actor_label="actor",
            actor=actor,
            note=note,
        ),
    )
    write_entity(item_path, frontmatter=frontmatter, body=body)
    return item_path
