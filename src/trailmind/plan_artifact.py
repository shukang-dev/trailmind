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


# --- Creation ---

from trailmind.entity_io import write_entity
from trailmind.ids import slugify
from trailmind.log import action_activity_entry
from trailmind.roster import Roster
from trailmind.scopes import resolve_epic_dir


def _resolve_roster_developer(roster: Roster, raw: str) -> tuple[str, str]:
    normalized = raw.strip().lower()
    for developer in roster.developers:
        if developer.email == normalized or developer.shortname.lower() == normalized:
            return developer.shortname, developer.uid
    raise TrailmindError(f"{normalized} is not registered in roster.yaml")


def create_spec(
    repo_root: Path,
    *,
    epic_ref: str,
    title: str,
    author: str,
    scope: str | None = None,
    status: str = "draft-for-review",
) -> Path:
    if status not in SPEC_STATUSES:
        raise TrailmindError(f"invalid spec status {status!r}; expected one of: {', '.join(SPEC_STATUSES)}")
    epic_path = resolve_epic_dir(repo_root, epic_ref)
    roster = Roster.load(repo_root / "roster.yaml")
    author_shortname, _author_uid = _resolve_roster_developer(roster, author)

    specs_dir = epic_path / "docs" / "specs"
    _ensure_doc_dir(specs_dir, "specs")
    today = date.today().isoformat()
    filename = f"{today}-{slugify(title)}.md"
    spec_path = specs_dir / filename

    if spec_path.exists():
        raise TrailmindError(f"spec already exists: {spec_path.relative_to(repo_root).as_posix()}")

    write_entity(
        spec_path,
        frontmatter={
            "title": title,
            "status": status,
            "created": today,
            "scope": scope,
            "project": _project_from_epic(epic_path),
            "epic": _epic_from_path(epic_path),
            "linked_plans": [],
        },
        body=_spec_body(title, author_shortname, today),
    )
    return spec_path


def create_plan(
    repo_root: Path,
    *,
    epic_ref: str,
    title: str,
    author: str,
    spec_ref: str | None = None,
    scope: str | None = None,
    status: str = "draft",
) -> Path:
    if status not in PLAN_STATUSES:
        raise TrailmindError(f"invalid plan status {status!r}; expected one of: {', '.join(PLAN_STATUSES)}")
    epic_path = resolve_epic_dir(repo_root, epic_ref)
    roster = Roster.load(repo_root / "roster.yaml")
    author_shortname, _author_uid = _resolve_roster_developer(roster, author)

    plans_dir = epic_path / "docs" / "plans"
    _ensure_doc_dir(plans_dir, "plans")
    today = date.today().isoformat()
    filename = f"{today}-{slugify(title)}.md"
    plan_path = plans_dir / filename

    if plan_path.exists():
        raise TrailmindError(f"plan already exists: {plan_path.relative_to(repo_root).as_posix()}")

    # Resolve linked spec relative to epic
    linked_spec_epic_rel = None
    if spec_ref:
        spec_abs = _resolve_doc_ref(repo_root, epic_path, spec_ref, "spec")
        linked_spec_epic_rel = spec_abs.relative_to(epic_path).as_posix()

    write_entity(
        plan_path,
        frontmatter={
            "title": title,
            "status": status,
            "created": today,
            "scope": scope,
            "project": _project_from_epic(epic_path),
            "epic": _epic_from_path(epic_path),
            "linked_spec": linked_spec_epic_rel,
            "generated_tasks": [],
        },
        body=_plan_body(title, author_shortname, today),
    )

    # Update spec's linked_plans if spec was provided
    if spec_ref:
        spec_abs = _resolve_doc_ref(repo_root, epic_path, spec_ref, "spec")
        _append_linked_plan(repo_root, spec_abs, plan_path.relative_to(epic_path).as_posix())

    return plan_path


def _ensure_doc_dir(path: Path, label: str) -> None:
    if path.exists() and not path.is_dir():
        raise TrailmindError(f"{label} path {path} is not a directory")
    path.mkdir(parents=True, exist_ok=True)


def _project_from_epic(epic_path: Path) -> str | None:
    parts = epic_path.parts
    try:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except (ValueError, IndexError):
        pass
    return None


def _epic_from_path(epic_path: Path) -> str | None:
    return epic_path.name


def _resolve_doc_ref(repo_root: Path, epic_path: Path, ref: str, label: str) -> Path:
    ref = ref.strip()
    candidate = repo_root / Path(*PurePosixPath(ref).parts)
    if candidate.exists():
        return candidate
    candidate = epic_path / Path(*PurePosixPath(ref).parts)
    if candidate.exists():
        return candidate
    raise TrailmindError(f"{label} not found: {ref}")


def _append_linked_plan(repo_root: Path, spec_path: Path, plan_epic_rel: str) -> None:
    from trailmind.log import read_entity_user_facing

    frontmatter, body = read_entity_user_facing(spec_path, label="spec")
    linked_plans = frontmatter.get("linked_plans", [])
    if not isinstance(linked_plans, list):
        linked_plans = []
    if plan_epic_rel not in linked_plans:
        linked_plans.append(plan_epic_rel)
    frontmatter["linked_plans"] = linked_plans
    write_entity(spec_path, frontmatter=frontmatter, body=body)


def _spec_body(title: str, author: str, today: str) -> str:
    return (
        f"# {title}\n\n"
        "## Purpose\n\n\n"
        "## Goals\n\n\n"
        "## Non-Goals\n\n\n"
        "## Design\n\n\n"
        "## Open Questions\n\n\n"
        "## Activity Log\n\n"
        f"{action_activity_entry(action='Created', actor_label='author', actor=author)}\n"
    )


def _plan_body(title: str, author: str, today: str) -> str:
    return (
        f"# {title}\n\n"
        "## Scope\n\n\n"
        "## Architecture\n\n\n"
        "## Tasks\n\n\n"
        "## Activity Log\n\n"
        f"{action_activity_entry(action='Created', actor_label='author', actor=author)}\n"
    )
