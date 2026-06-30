import pytest

from trailmind.errors import TrailmindError
from trailmind.task_status import (
    TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    is_terminal_task_status,
    normalize_task_status,
    validate_task_status,
    validate_task_transition,
)


def test_task_statuses_are_canonical_order():
    assert TASK_STATUSES == ("created", "ready", "in_progress", "blocked", "done", "wontfix")
    assert TERMINAL_TASK_STATUSES == ("done", "wontfix")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("created", "created"),
        ("ready", "ready"),
        ("in_progress", "in_progress"),
        ("blocked", "blocked"),
        ("done", "done"),
        ("wontfix", "wontfix"),
        ("planned", "created"),
        ("integration", "in_progress"),
        ("  planned  ", "created"),
    ],
)
def test_normalize_task_status_accepts_current_and_legacy_values(raw: str, expected: str):
    assert normalize_task_status(raw) == expected


def test_validate_task_status_rejects_unknown_status():
    with pytest.raises(TrailmindError, match="invalid task status"):
        validate_task_status("paused")


@pytest.mark.parametrize("status", ["done", "wontfix"])
def test_is_terminal_task_status_accepts_terminal_values(status: str):
    assert is_terminal_task_status(status) is True


@pytest.mark.parametrize(
    "status",
    ["created", "ready", "in_progress", "blocked", "planned", "integration"],
)
def test_is_terminal_task_status_rejects_non_terminal_values(status: str):
    assert is_terminal_task_status(status) is False


def test_is_terminal_task_status_rejects_unknown_status():
    with pytest.raises(TrailmindError, match="invalid task status"):
        is_terminal_task_status("paused")


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("created", "ready"),
        ("created", "in_progress"),
        ("created", "blocked"),
        ("created", "wontfix"),
        ("ready", "in_progress"),
        ("ready", "blocked"),
        ("ready", "done"),
        ("ready", "wontfix"),
        ("in_progress", "ready"),
        ("in_progress", "blocked"),
        ("in_progress", "done"),
        ("in_progress", "wontfix"),
        ("blocked", "ready"),
        ("blocked", "in_progress"),
        ("blocked", "wontfix"),
        ("planned", "ready"),
        ("integration", "done"),
    ],
)
def test_validate_task_transition_accepts_allowed_moves(current: str, target: str):
    assert validate_task_transition(current, target) == (normalize_task_status(current), target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("created", "done"),
        ("blocked", "done"),
        ("done", "ready"),
        ("wontfix", "ready"),
    ],
)
def test_validate_task_transition_rejects_disallowed_moves(current: str, target: str):
    with pytest.raises(TrailmindError, match="invalid task status transition"):
        validate_task_transition(current, target)
