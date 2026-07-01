from pathlib import Path

import pytest

from trailmind.errors import TrailmindError
from trailmind.pickup import (
    build_base_pickup_pack,
    excerpt_file,
    extract_activity_entries,
    extract_markdown_section,
    pickup_pack_to_dict,
)


def test_extract_markdown_section_returns_named_section_body():
    body = "# Title\n\n## Scope\n\nBuild it.\n\n## Acceptance\n\n- Works\n\n## Activity Log\n\n- entry\n"

    assert extract_markdown_section(body, "Scope") == "Build it."
    assert extract_markdown_section(body, "Acceptance") == "- Works"
    assert extract_markdown_section(body, "Missing") is None


def test_extract_markdown_section_strips_heading_whitespace():
    indented_heading = "# Title\n\n  ## Scope  \n\nBuild it.\n"
    indented_next_heading = "# Title\n\n## Scope\n\nBuild it.\n\n  ## Acceptance  \n\n- Works\n"

    assert extract_markdown_section(indented_heading, "Scope") == "Build it."
    assert extract_markdown_section(indented_next_heading, "Scope") == "Build it."


def test_extract_activity_entries_returns_recent_entries():
    body = (
        "# Task\n\n"
        "## Activity Log\n\n"
        "- 2026-07-01: First.\n"
        "- 2026-07-02: Second.\n"
        "- 2026-07-03: Third.\n"
    )

    assert extract_activity_entries(body, limit=2) == [
        "- 2026-07-02: Second.",
        "- 2026-07-03: Third.",
    ]


def test_extract_activity_entries_rejects_non_positive_limit():
    with pytest.raises(TrailmindError, match="activity limit must be at least 1"):
        extract_activity_entries("## Activity Log\n\n- entry\n", limit=0)


def test_excerpt_file_truncates_text_files(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    excerpt = excerpt_file(tmp_path, "src/app.py", max_lines=2)

    assert excerpt["path"] == "src/app.py"
    assert excerpt["start_line"] == 1
    assert excerpt["end_line"] == 2
    assert excerpt["total_lines"] == 3
    assert excerpt["truncated"] is True
    assert excerpt["content"] == "one\ntwo"
    assert excerpt["skipped"] is False


def test_excerpt_file_reports_missing_files(tmp_path: Path):
    excerpt = excerpt_file(tmp_path, "src/missing.py", max_lines=80)

    assert excerpt["path"] == "src/missing.py"
    assert excerpt["skipped"] is True
    assert excerpt["skip_reason"] == "missing"


def test_excerpt_file_rejects_path_escape(tmp_path: Path):
    with pytest.raises(TrailmindError, match="referenced path escapes repository"):
        excerpt_file(tmp_path, "../secret.txt", max_lines=80)


def test_excerpt_file_rejects_non_positive_max_lines(tmp_path: Path):
    with pytest.raises(TrailmindError, match="max lines must be at least 1"):
        excerpt_file(tmp_path, "src/app.py", max_lines=0)


def test_base_pickup_pack_dict_shape():
    pack = build_base_pickup_pack(kind="task", repo_path="projects/demo/mvp/tasks/T-123456-001-demo.md")

    data = pickup_pack_to_dict(pack)

    assert data["kind"] == "task"
    assert data["item"]["path"] == "projects/demo/mvp/tasks/T-123456-001-demo.md"
    assert data["dependencies"] == {}
    assert data["linked_items"] == {}
    assert data["deliverables"] == {}
    assert data["activity"] == []
    assert data["excerpts"] == []
    assert data["next_actions"] == []
    assert data["warnings"] == []
