from __future__ import annotations

from trailmind.errors import TrailmindError


TASK_STATUSES = ("created", "ready", "in_progress", "blocked", "done", "wontfix")
TERMINAL_TASK_STATUSES = ("done", "wontfix")
STATUS_NORMALIZATIONS = {
    "planned": "created",
    "integration": "in_progress",
}
ALLOWED_TASK_TRANSITIONS = {
    "created": ("ready", "in_progress", "blocked", "wontfix"),
    "ready": ("in_progress", "blocked", "done", "wontfix"),
    "in_progress": ("ready", "blocked", "done", "wontfix"),
    "blocked": ("ready", "in_progress", "wontfix"),
    "done": (),
    "wontfix": (),
}


def normalize_task_status(status: object) -> str:
    raw = str(status or "").strip()
    normalized = STATUS_NORMALIZATIONS.get(raw, raw)
    return validate_task_status(normalized)


def validate_task_status(status: object) -> str:
    raw = str(status or "").strip()
    if raw not in TASK_STATUSES:
        expected = ", ".join(TASK_STATUSES)
        raise TrailmindError(f"invalid task status {raw!r}; expected one of: {expected}")
    return raw


def validate_task_transition(current: object, target: object) -> tuple[str, str]:
    normalized_current = normalize_task_status(current)
    normalized_target = validate_task_status(target)
    if normalized_target not in ALLOWED_TASK_TRANSITIONS[normalized_current]:
        raise TrailmindError(
            f"invalid task status transition {normalized_current!r} -> {normalized_target!r}"
        )
    return normalized_current, normalized_target


def is_terminal_task_status(status: object) -> bool:
    return normalize_task_status(status) in TERMINAL_TASK_STATUSES
