from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.entity_io import EntityFormatError, read_entity
from trailmind.errors import TrailmindError


SPEC_STATUSES = (
    "draft-for-review",
    "approved-for-spec",
    "approved-for-implementation",
    "superseded",
)

PLAN_STATUSES = (
    "draft",
    "approved",
    "in-progress",
    "completed",
    "superseded",
)

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class SpecInfo:
    path: str
    title: str
    status: str
    created: str | None
    scope: str | None
    project: str | None
    epic: str | None
    linked_plans: list[str]


@dataclass(frozen=True)
class PlanInfo:
    path: str
    title: str
    status: str
    created: str | None
    scope: str | None
    project: str | None
    epic: str | None
    linked_spec: str | None
    generated_tasks: list[str]


def parse_spec_info(text: str, *, path: str) -> SpecInfo:
    frontmatter, body = _try_read_frontmatter(text)
    if frontmatter:
        title = _require_field(frontmatter, "title", "spec")
        status = frontmatter.get("status", "draft-for-review")
        created = _string_or_none(frontmatter.get("created"))
        scope = _string_or_none(frontmatter.get("scope"))
        project = _string_or_none(frontmatter.get("project"))
        epic = _string_or_none(frontmatter.get("epic"))
        linked_plans = _string_list(frontmatter.get("linked_plans"))
    else:
        title = _title_from_body(body, path)
        status = "draft-for-review"
        created = None
        scope = None
        project = None
        epic = None
        linked_plans = []
    return SpecInfo(
        path=path,
        title=title,
        status=status,
        created=created,
        scope=scope,
        project=project,
        epic=epic,
        linked_plans=linked_plans,
    )


def parse_plan_info(text: str, *, path: str) -> PlanInfo:
    frontmatter, body = _try_read_frontmatter(text)
    if frontmatter:
        title = _require_field(frontmatter, "title", "plan")
        status = frontmatter.get("status", "draft")
        created = _string_or_none(frontmatter.get("created"))
        scope = _string_or_none(frontmatter.get("scope"))
        project = _string_or_none(frontmatter.get("project"))
        epic = _string_or_none(frontmatter.get("epic"))
        linked_spec = _string_or_none(frontmatter.get("linked_spec"))
        generated_tasks = _string_list(frontmatter.get("generated_tasks"))
    else:
        title = _title_from_body(body, path)
        status = "draft"
        created = None
        scope = None
        project = None
        epic = None
        linked_spec = None
        generated_tasks = []
    return PlanInfo(
        path=path,
        title=title,
        status=status,
        created=created,
        scope=scope,
        project=project,
        epic=epic,
        linked_spec=linked_spec,
        generated_tasks=generated_tasks,
    )


def _try_read_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Try to parse YAML frontmatter. Returns (frontmatter_dict or None, body)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    try:
        import yaml
        raw = match.group(1)
        loaded = yaml.safe_load(raw)
        if loaded is None and raw.strip() == "":
            loaded = {}
        if not isinstance(loaded, dict):
            return None, text
        body = text[match.end():]
        return loaded, body
    except Exception:
        return None, text


def _require_field(frontmatter: dict[str, Any], key: str, label: str) -> str:
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TrailmindError(f"{label} is missing a required '{key}' field")
    return value.strip()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _title_from_body(body: str, path: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return Path(path).stem
