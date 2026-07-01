from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.errors import TrailmindError


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class PickupPack:
    kind: str
    generated_at: str
    item: dict[str, Any]
    dependencies: dict[str, Any] = field(default_factory=dict)
    linked_items: dict[str, Any] = field(default_factory=dict)
    deliverables: dict[str, Any] = field(default_factory=dict)
    activity: list[str] = field(default_factory=list)
    excerpts: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_base_pickup_pack(*, kind: str, repo_path: str) -> PickupPack:
    return PickupPack(
        kind=kind,
        generated_at=date.today().isoformat(),
        item={"path": repo_path},
    )


def pickup_pack_to_dict(pack: PickupPack) -> dict[str, Any]:
    return {
        "kind": pack.kind,
        "generated_at": pack.generated_at,
        "item": pack.item,
        "dependencies": pack.dependencies,
        "linked_items": pack.linked_items,
        "deliverables": pack.deliverables,
        "activity": pack.activity,
        "excerpts": pack.excerpts,
        "next_actions": pack.next_actions,
        "warnings": pack.warnings,
    }


def extract_markdown_section(body: str, heading: str) -> str | None:
    wanted = heading.strip().casefold()
    lines = body.splitlines()
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line.strip())
        if not match:
            continue
        if start is None and match.group(1).strip().casefold() == wanted:
            start = index + 1
            continue
        if start is not None:
            end = index
            break
    if start is None:
        return None
    text = "\n".join(lines[start:end]).strip()
    return text or None


def extract_activity_entries(body: str, *, limit: int) -> list[str]:
    if limit < 1:
        raise TrailmindError("activity limit must be at least 1")
    section = extract_markdown_section(body, "Activity Log")
    if not section:
        return []
    entries = [line.strip() for line in section.splitlines() if line.strip().startswith("- ")]
    return entries[-limit:]


def _safe_relative_path(raw: str) -> Path:
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        not raw.strip()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        raise TrailmindError(f"referenced path escapes repository: {raw}")
    return Path(*posix_path.parts)


def excerpt_file(repo_root: Path, raw_path: str, *, max_lines: int) -> dict[str, Any]:
    if max_lines < 1:
        raise TrailmindError("max lines must be at least 1")
    relative = _safe_relative_path(raw_path)
    display_path = relative.as_posix()
    path = repo_root / relative
    try:
        path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"referenced path escapes repository: {raw_path}") from exc
    if not path.exists():
        return {"path": display_path, "skipped": True, "skip_reason": "missing"}
    if path.is_dir():
        return {"path": display_path, "skipped": True, "skip_reason": "directory"}
    selected: list[str] = []
    total_lines = 0
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                total_lines += 1
                if len(selected) < max_lines:
                    selected.append(line.rstrip("\n"))
    except UnicodeDecodeError:
        return {"path": display_path, "skipped": True, "skip_reason": "non-utf-8"}
    except OSError as exc:
        return {"path": display_path, "skipped": True, "skip_reason": str(exc)}
    return {
        "path": display_path,
        "start_line": 1 if total_lines else 0,
        "end_line": len(selected),
        "total_lines": total_lines,
        "truncated": total_lines > max_lines,
        "content": "\n".join(selected),
        "skipped": False,
    }
