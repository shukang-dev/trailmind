from pathlib import Path

import pytest

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.errors import TrailmindError
from trailmind.plan_artifact import (
    PLAN_STATUSES,
    SPEC_STATUSES,
    PlanInfo,
    SpecInfo,
    parse_plan_info,
    parse_spec_info,
)


def _repo_with_epic(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n"
        "  shortname: alice\n"
        "  uid: '123456'\n"
        "  name: Alice\n"
        "- email: bob@example.com\n"
        "  shortname: bob\n"
        "  uid: '654321'\n"
        "  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    assert runner.invoke(
        cli,
        ["project", "init", "--slug", "demo_app", "--title", "Demo App", "--goal", "Build a useful demo."],
        obj={"cwd": tmp_path},
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "epic", "init",
            "--project", "demo_app",
            "--slug", "mvp",
            "--title", "MVP",
            "--goal", "First usable release",
            "--roster", "alice",
            "--repos", "demo_app",
        ],
        obj={"cwd": tmp_path},
    ).exit_code == 0
    return tmp_path


SPEC_TEXT = """---
title: Parser Redesign
status: draft-for-review
created: '2026-07-02'
scope: v0.5-parser
project: demo_app
epic: mvp
linked_plans: []
---

# Parser Redesign

## Purpose

Make parsing faster.

## Goals

- Speed
"""


PLAN_TEXT = """---
title: Parser Implementation
status: draft
created: '2026-07-02'
scope: v0.5-parser
project: demo_app
epic: mvp
linked_spec: docs/specs/2026-07-02-parser-redesign.md
generated_tasks: []
---

# Parser Implementation

## Scope

Implement the parser redesign.
"""


def test_parse_spec_info_extracts_frontmatter():
    info = parse_spec_info(SPEC_TEXT, path="projects/demo_app/mvp/docs/specs/2026-07-02-parser-redesign.md")

    assert isinstance(info, SpecInfo)
    assert info.title == "Parser Redesign"
    assert info.status == "draft-for-review"
    assert info.created == "2026-07-02"
    assert info.scope == "v0.5-parser"
    assert info.project == "demo_app"
    assert info.epic == "mvp"
    assert info.linked_plans == []


def test_parse_spec_info_requires_title():
    with pytest.raises(TrailmindError, match="spec is missing"):
        parse_spec_info("---\nstatus: draft\n---\n# No title\n", path="x.md")


def test_parse_plan_info_extracts_frontmatter():
    info = parse_plan_info(PLAN_TEXT, path="projects/demo_app/mvp/docs/plans/2026-07-02-parser-implementation.md")

    assert isinstance(info, PlanInfo)
    assert info.title == "Parser Implementation"
    assert info.status == "draft"
    assert info.created == "2026-07-02"
    assert info.linked_spec == "docs/specs/2026-07-02-parser-redesign.md"
    assert info.generated_tasks == []


def test_parse_plan_info_works_with_legacy_plan_no_frontmatter():
    legacy = "# My Plan\n\n### Task 1: Do stuff\n\nBody.\n"

    info = parse_plan_info(legacy, path="projects/demo_app/mvp/docs/plans/my-plan.md")

    assert info.title == "My Plan"
    assert info.status == "draft"
    assert info.linked_spec is None
    assert info.generated_tasks == []


def test_spec_statuses_are_defined():
    assert "draft-for-review" in SPEC_STATUSES
    assert "approved-for-spec" in SPEC_STATUSES
    assert "approved-for-implementation" in SPEC_STATUSES
    assert "superseded" in SPEC_STATUSES


def test_plan_statuses_are_defined():
    assert "draft" in PLAN_STATUSES
    assert "approved" in PLAN_STATUSES
    assert "in-progress" in PLAN_STATUSES
    assert "completed" in PLAN_STATUSES
    assert "superseded" in PLAN_STATUSES


# --- Task 2: Spec and Plan Creation ---

from trailmind.plan_artifact import create_plan, create_spec


def test_create_spec_writes_file_with_frontmatter(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_spec(
        repo,
        epic_ref="projects/demo_app/mvp",
        title="Parser Redesign",
        author="alice@example.com",
        scope="v0.5-parser",
        status="draft-for-review",
    )

    assert path.exists()
    assert "docs/specs/" in str(path)
    frontmatter, body = read_entity(path)
    assert frontmatter["title"] == "Parser Redesign"
    assert frontmatter["status"] == "draft-for-review"
    assert frontmatter["scope"] == "v0.5-parser"
    assert frontmatter["linked_plans"] == []
    assert "Parser Redesign" in body
    assert "## Purpose" in body
    assert "## Activity Log" in body
    assert "alice" in body


def test_create_spec_resolves_author_by_shortname(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_spec(
        repo,
        epic_ref="projects/demo_app/mvp",
        title="Another Spec",
        author="alice",
    )

    assert path.exists()
    _, body = read_entity(path)
    assert "alice" in body


def test_create_plan_writes_file_with_frontmatter(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_plan(
        repo,
        epic_ref="projects/demo_app/mvp",
        title="Parser Implementation",
        author="alice@example.com",
        scope="v0.5-parser",
        status="draft",
    )

    assert path.exists()
    assert "docs/plans/" in str(path)
    frontmatter, body = read_entity(path)
    assert frontmatter["title"] == "Parser Implementation"
    assert frontmatter["status"] == "draft"
    assert frontmatter["generated_tasks"] == []
    assert "Parser Implementation" in body
    assert "## Scope" in body
    assert "## Activity Log" in body


def test_create_plan_with_linked_spec(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    spec_path = create_spec(
        repo,
        epic_ref="projects/demo_app/mvp",
        title="My Spec",
        author="alice",
    )
    plan_path = create_plan(
        repo,
        epic_ref="projects/demo_app/mvp",
        title="My Plan",
        author="alice",
        spec_ref=str(spec_path.relative_to(repo)),
    )

    plan_fm, _ = read_entity(plan_path)
    assert plan_fm["linked_spec"] is not None

    spec_fm, _ = read_entity(spec_path)
    assert len(spec_fm["linked_plans"]) == 1


def test_create_spec_rejects_missing_epic(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    with pytest.raises(TrailmindError, match="epic"):
        create_spec(repo, epic_ref="projects/demo_app/missing", title="X", author="alice")


def test_create_spec_rejects_unknown_author(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    with pytest.raises(TrailmindError, match="not registered"):
        create_spec(repo, epic_ref="projects/demo_app/mvp", title="X", author="unknown@example.com")
