from pathlib import Path

import pytest

from trailmind.ids import EntityId, next_entity_id, parse_entity_id, slugify
from trailmind.paths import find_repo_root


def test_parse_task_id():
    assert parse_entity_id("T-123456-007") == EntityId(entity="T", uid="123456", number=7)


def test_parse_milestone_id():
    assert parse_entity_id("M-012") == EntityId(entity="M", uid=None, number=12)


def test_parse_rejects_invalid_id():
    with pytest.raises(ValueError, match="invalid entity id"):
        parse_entity_id("TASK-1")


def test_next_entity_id_uses_existing_files(tmp_path: Path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "T-123456-001-first.md").write_text("", encoding="utf-8")
    (tasks / "T-123456-003-third.md").write_text("", encoding="utf-8")
    (tasks / "T-654321-001-other.md").write_text("", encoding="utf-8")

    assert next_entity_id(tasks, entity="T", uid="123456") == "T-123456-004"


def test_next_milestone_id(tmp_path: Path):
    milestones = tmp_path / "milestones"
    milestones.mkdir()
    (milestones / "M-001-alpha.md").write_text("", encoding="utf-8")

    assert next_entity_id(milestones, entity="M") == "M-002"


def test_slugify_title():
    assert slugify("Build CLI: Task Add!") == "build-cli-task-add"


def test_find_repo_root(tmp_path: Path):
    repo = tmp_path / "repo"
    nested = repo / "projects" / "demo"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()

    assert find_repo_root(nested) == repo
