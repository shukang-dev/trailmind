from pathlib import Path

import pytest

from trailmind.entity_io import EntityFormatError, read_entity, write_entity


def test_write_and_read_entity_round_trip(tmp_path: Path):
    path = tmp_path / "tasks" / "T-123456-001-demo.md"
    write_entity(
        path,
        frontmatter={
            "id": "T-123456-001",
            "title": "Demo task",
            "created": "2026-06-29",
            "depends_on": [],
        },
        body="## Scope\n\nBuild the demo.\n",
    )

    frontmatter, body = read_entity(path)

    assert frontmatter["id"] == "T-123456-001"
    assert frontmatter["title"] == "Demo task"
    assert frontmatter["created"] == "2026-06-29"
    assert frontmatter["depends_on"] == []
    assert body == "## Scope\n\nBuild the demo.\n"


def test_read_entity_rejects_missing_frontmatter(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("plain markdown\n", encoding="utf-8")

    with pytest.raises(EntityFormatError, match="missing YAML frontmatter"):
        read_entity(path)


def test_update_preserves_body(tmp_path: Path):
    path = tmp_path / "issue.md"
    write_entity(path, frontmatter={"id": "I-123456-001", "status": "open"}, body="## Description\n\nBug.\n")
    write_entity(path, frontmatter={"id": "I-123456-001", "status": "done"}, body=read_entity(path)[1])

    frontmatter, body = read_entity(path)
    assert frontmatter["status"] == "done"
    assert body == "## Description\n\nBug.\n"


def test_round_trip_quotes_unchanged_strings_yaml_would_reinterpret(tmp_path: Path):
    path = tmp_path / "task.md"
    path.write_text("---\nflag: yes\n---\nbody\n", encoding="utf-8")

    write_entity(path, frontmatter={"flag": "yes"}, body="body\n")

    text = path.read_text(encoding="utf-8")
    assert "flag: 'yes'" in text
    frontmatter, body = read_entity(path)
    assert frontmatter["flag"] == "yes"
    assert body == "body\n"


def test_round_trip_quotes_nested_strings_yaml_would_reinterpret(tmp_path: Path):
    path = tmp_path / "task.md"
    path.write_text("---\ntags: [yes]\nmetadata:\n  flag: no\n---\nbody\n", encoding="utf-8")

    write_entity(path, frontmatter={"tags": ["yes"], "metadata": {"flag": "no"}}, body="body\n")

    text = path.read_text(encoding="utf-8")
    assert "'yes'" in text
    assert "'no'" in text
    frontmatter, body = read_entity(path)
    assert frontmatter == {"tags": ["yes"], "metadata": {"flag": "no"}}
    assert body == "body\n"


def test_round_trip_preserves_safe_nested_comments_while_quoting_unsafe_sibling(tmp_path: Path):
    path = tmp_path / "task.md"
    path.write_text(
        "---\nmetadata:\n  safe: unchanged # keep me\n  flag: yes\n---\nbody\n",
        encoding="utf-8",
    )

    write_entity(path, frontmatter={"metadata": {"safe": "unchanged", "flag": "yes"}}, body="body\n")

    text = path.read_text(encoding="utf-8")
    assert "safe: unchanged # keep me" in text
    assert "flag: 'yes'" in text
    frontmatter, body = read_entity(path)
    assert frontmatter == {"metadata": {"safe": "unchanged", "flag": "yes"}}
    assert body == "body\n"
