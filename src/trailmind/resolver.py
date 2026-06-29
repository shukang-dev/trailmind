from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from trailmind.errors import TrailmindError


ENTITY_FOLDERS = {
    "T": "tasks",
    "I": "issues",
    "M": "milestones",
}
SLUG_SUFFIX_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EntityNotFoundError(TrailmindError):
    """Raised when an entity reference cannot be resolved."""


class EntityAmbiguousError(TrailmindError):
    """Raised when an entity reference resolves to multiple candidates."""


def _entity_folder(entity: str) -> str:
    key = entity.strip().upper()
    if key not in ENTITY_FOLDERS:
        expected = ", ".join(sorted(ENTITY_FOLDERS))
        raise TrailmindError(f"unsupported entity {entity!r}; expected one of: {expected}")
    return ENTITY_FOLDERS[key]


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


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_direct_path(repo_root: Path, raw: str) -> Path:
    windows_path = PureWindowsPath(raw)
    if PurePosixPath(raw).is_absolute() or windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise EntityNotFoundError(f"entity path {raw!r} not found")
    if _has_parent_reference(raw):
        raise EntityNotFoundError(f"entity path {raw!r} not found")

    candidate = repo_root / raw
    try:
        candidate.resolve(strict=False).relative_to(repo_root.resolve())
    except (OSError, RuntimeError) as exc:
        raise EntityNotFoundError(f"entity path {raw!r} could not resolve") from exc
    except ValueError as exc:
        raise EntityNotFoundError(f"entity path {raw!r} not found outside repository") from exc

    if candidate.is_file():
        return candidate
    raise EntityNotFoundError(f"entity path {raw!r} not found")


def _matches_bare_id(path: Path, raw: str) -> bool:
    stem = path.stem
    if stem == raw:
        return True
    prefix = f"{raw}-"
    if not stem.startswith(prefix):
        return False
    return bool(SLUG_SUFFIX_RE.fullmatch(stem[len(prefix) :]))


def resolve_entity(repo_root: Path, *, raw: str, entity: str) -> Path:
    """Resolve an entity reference to a single Markdown file path."""
    folder = _entity_folder(entity)
    if not raw:
        raise EntityNotFoundError("entity not found: empty reference")

    if _is_path_like(raw):
        return _resolve_direct_path(repo_root, raw)

    search_root = repo_root / "projects"
    matches = sorted(
        (
            path
            for path in search_root.glob(f"*/*/{folder}/*.md")
            if path.is_file() and _matches_bare_id(path, raw)
        ),
        key=lambda path: _relative_display(path, repo_root),
    )

    if not matches:
        raise EntityNotFoundError(f"{entity} entity {raw!r} not found")
    if len(matches) > 1:
        candidates = ", ".join(_relative_display(path, repo_root) for path in matches)
        raise EntityAmbiguousError(f"{entity} entity {raw!r} is ambiguous; candidates: {candidates}")
    return matches[0]
