from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ID_RE = re.compile(r"^(?P<entity>[TI])-(?P<uid>\d{6})-(?P<number>\d{3,})$")
MILESTONE_RE = re.compile(r"^M-(?P<number>\d{3,})$")


@dataclass(frozen=True)
class EntityId:
    entity: str
    uid: str | None
    number: int


def parse_entity_id(raw: str) -> EntityId:
    match = ID_RE.match(raw)
    if match:
        return EntityId(
            entity=match.group("entity"),
            uid=match.group("uid"),
            number=int(match.group("number")),
        )
    milestone = MILESTONE_RE.match(raw)
    if milestone:
        return EntityId(entity="M", uid=None, number=int(milestone.group("number")))
    raise ValueError(f"invalid entity id: {raw}")


def format_entity_id(entity: str, number: int, uid: str | None = None) -> str:
    if entity == "M":
        return f"M-{number:03d}"
    if uid is None:
        raise ValueError("uid is required for Task and Issue IDs")
    return f"{entity}-{uid}-{number:03d}"


def next_entity_id(folder: Path, *, entity: str, uid: str | None = None) -> str:
    max_number = 0
    if folder.exists():
        for path in folder.iterdir():
            stem = path.name.split("-", 3)
            raw = "-".join(stem[:3]) if entity in {"T", "I"} else "-".join(stem[:2])
            try:
                parsed = parse_entity_id(raw)
            except ValueError:
                continue
            if parsed.entity != entity:
                continue
            if entity in {"T", "I"} and parsed.uid != uid:
                continue
            max_number = max(max_number, parsed.number)
    return format_entity_id(entity, max_number + 1, uid)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "untitled"
