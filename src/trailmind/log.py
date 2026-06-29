from __future__ import annotations

from datetime import date
from pathlib import Path

from trailmind.entity_io import EntityFormatError, read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.resolver import resolve_entity


ENTITY_NAMES = {
    "I": "issue",
    "M": "milestone",
    "T": "task",
}
ENTITY_ALIASES = {
    "I": "I",
    "ISSUE": "I",
    "M": "M",
    "MILESTONE": "M",
    "T": "T",
    "TASK": "T",
}


def _normalize_entity(entity: str) -> str:
    key = entity.strip().upper()
    if key in ENTITY_ALIASES:
        return ENTITY_ALIASES[key]
    expected = ", ".join(sorted(ENTITY_NAMES))
    raise TrailmindError(f"log entity must be one of: {expected}")


def _entity_key(raw: str) -> str:
    if not raw:
        raise TrailmindError("entity reference is required")
    ref = raw.strip()
    if ref:
        key = ref[0].upper()
        if key in ENTITY_NAMES:
            return key
    parts = ref.replace("\\", "/").split("/")
    if "issues" in parts:
        return "I"
    if "milestones" in parts:
        return "M"
    if "tasks" in parts:
        return "T"
    expected = ", ".join(sorted(ENTITY_NAMES))
    raise TrailmindError(f"log entity must start with one of: {expected}")


def read_entity_user_facing(path: Path, *, label: str) -> tuple[dict[str, object], str]:
    try:
        return read_entity(path)
    except EntityFormatError as exc:
        raise TrailmindError(str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise TrailmindError(f"could not read {label} file {path}: file must be valid UTF-8") from exc
    except OSError as exc:
        raise TrailmindError(f"could not read {label} file {path}: {exc}") from exc


def normalize_activity_text(value: str) -> str:
    return " ".join(value.split())


def activity_actor(value: str) -> str:
    sanitized = normalize_activity_text(value)
    if not sanitized:
        raise TrailmindError("activity actor is required")
    return sanitized


def sanitized_activity_text(value: str, *, label: str, allow_blank: bool = False) -> str:
    """Compatibility wrapper for callers that already use the shared log sanitizer."""
    del label
    sanitized = normalize_activity_text(value)
    if not sanitized and not allow_blank:
        raise TrailmindError("activity actor is required")
    return sanitized


def generic_activity_entry(*, author: str, note: str) -> str:
    sanitized_author = activity_actor(author)
    sanitized_note = normalize_activity_text(note)
    entry = f"- {date.today().isoformat()}: Note by {sanitized_author}."
    if sanitized_note:
        entry = f"{entry} {sanitized_note}"
    return entry


def action_activity_entry(*, action: str, actor_label: str, actor: str, note: str | None = None) -> str:
    del actor_label
    sanitized_actor = activity_actor(actor)
    entry = f"- {date.today().isoformat()}: {action} by {sanitized_actor}."
    if note is not None:
        sanitized_note = normalize_activity_text(note)
        if sanitized_note:
            entry = f"{entry} {sanitized_note}"
    return entry


def append_activity_entry(body: str, entry: str) -> str:
    text = body.rstrip("\n")
    if not text:
        return f"## Activity Log\n\n{entry}\n"

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "## Activity Log":
            continue

        section_end = len(lines)
        for cursor in range(index + 1, len(lines)):
            if lines[cursor].startswith("## "):
                section_end = cursor
                break

        before = lines[:section_end]
        before.append(entry)
        after = lines[section_end:]
        if after:
            before.append("")
            before.extend(after)
        return "\n".join(before) + "\n"

    return f"{text}\n\n## Activity Log\n\n{entry}\n"


def append_log(repo_root: Path, *, raw_id: str, entity: str, author: str, note: str) -> Path:
    entity_key = _normalize_entity(entity)
    entity_path = resolve_entity(repo_root, raw=raw_id, entity=entity_key)
    frontmatter, body = read_entity_user_facing(entity_path, label=ENTITY_NAMES[entity_key])
    body = append_activity_entry(body, generic_activity_entry(author=author, note=note))
    write_entity(entity_path, frontmatter=frontmatter, body=body)
    return entity_path


def log_activity(repo_root: Path, *, entity_ref: str, author: str, note: str) -> Path:
    entity = _entity_key(entity_ref)
    return append_log(repo_root, raw_id=entity_ref, entity=entity, author=author, note=note)
