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


# --- Task 3: List, Show, Status, Link ---

from trailmind.plan_artifact import (
    link_plan_spec,
    list_plans,
    list_specs,
    set_plan_status,
    set_spec_status,
)


def test_list_specs_returns_specs_in_epic(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    create_spec(repo, epic_ref="projects/demo_app/mvp", title="Spec One", author="alice")
    create_spec(repo, epic_ref="projects/demo_app/mvp", title="Spec Two", author="bob")

    specs = list_specs(repo, epic_ref="projects/demo_app/mvp")

    assert len(specs) == 2
    titles = {s.title for s in specs}
    assert "Spec One" in titles
    assert "Spec Two" in titles


def test_list_specs_all_repo_when_no_epic(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    create_spec(repo, epic_ref="projects/demo_app/mvp", title="Only Spec", author="alice")

    specs = list_specs(repo)

    assert len(specs) == 1
    assert specs[0].title == "Only Spec"


def test_list_plans_returns_plans_in_epic(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    create_plan(repo, epic_ref="projects/demo_app/mvp", title="Plan One", author="alice")
    create_plan(repo, epic_ref="projects/demo_app/mvp", title="Plan Two", author="bob")

    plans = list_plans(repo, epic_ref="projects/demo_app/mvp")

    assert len(plans) == 2


def test_set_spec_status_updates_frontmatter_and_log(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Status Test", author="alice")

    set_spec_status(repo, spec_ref=str(path.relative_to(repo)), status="approved-for-spec", actor="alice")

    frontmatter, body = read_entity(path)
    assert frontmatter["status"] == "approved-for-spec"
    assert "approved-for-spec" in body or "Approved" in body


def test_set_spec_status_rejects_invalid_status(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Bad Status", author="alice")

    with pytest.raises(TrailmindError, match="invalid spec status"):
        set_spec_status(repo, spec_ref=str(path.relative_to(repo)), status="bogus", actor="alice")


def test_set_plan_status_updates_frontmatter(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = create_plan(repo, epic_ref="projects/demo_app/mvp", title="Plan Status", author="alice")

    set_plan_status(repo, plan_ref=str(path.relative_to(repo)), status="approved", actor="alice")

    frontmatter, body = read_entity(path)
    assert frontmatter["status"] == "approved"


def test_link_plan_spec_adds_bidirectional_refs(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    spec_path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Link Spec", author="alice")
    plan_path = create_plan(repo, epic_ref="projects/demo_app/mvp", title="Link Plan", author="alice")

    link_plan_spec(
        repo,
        plan_ref=str(plan_path.relative_to(repo)),
        spec_ref=str(spec_path.relative_to(repo)),
    )

    plan_fm, _ = read_entity(plan_path)
    assert plan_fm["linked_spec"] is not None

    spec_fm, _ = read_entity(spec_path)
    assert len(spec_fm["linked_plans"]) >= 1


def test_link_plan_spec_is_idempotent(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    spec_path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Idem Spec", author="alice")
    plan_path = create_plan(repo, epic_ref="projects/demo_app/mvp", title="Idem Plan", author="alice")
    ref = str(plan_path.relative_to(repo))
    sref = str(spec_path.relative_to(repo))

    link_plan_spec(repo, plan_ref=ref, spec_ref=sref)
    link_plan_spec(repo, plan_ref=ref, spec_ref=sref)

    spec_fm, _ = read_entity(spec_path)
    assert len(spec_fm["linked_plans"]) == 1


# --- Task 4: CLI Wiring ---

import json


def test_plan_spec_init_cli_creates_file(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "plan", "spec", "init",
            "--epic", "projects/demo_app/mvp",
            "--title", "CLI Spec",
            "--author", "alice@example.com",
            "--scope", "v0.5",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "docs/specs/" in result.output
    specs_dir = repo / "projects" / "demo_app" / "mvp" / "docs" / "specs"
    assert any(specs_dir.glob("*.md"))


def test_plan_spec_list_cli_shows_specs(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    CliRunner().invoke(cli, ["plan", "spec", "init", "--epic", "projects/demo_app/mvp",
                            "--title", "Listed Spec", "--author", "alice"], obj={"cwd": repo})

    result = CliRunner().invoke(
        cli,
        ["plan", "spec", "list", "--epic", "projects/demo_app/mvp"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "Listed Spec" in result.output


def test_plan_spec_list_cli_json(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    CliRunner().invoke(cli, ["plan", "spec", "init", "--epic", "projects/demo_app/mvp",
                            "--title", "JSON Spec", "--author", "alice"], obj={"cwd": repo})

    result = CliRunner().invoke(
        cli,
        ["plan", "spec", "list", "--epic", "projects/demo_app/mvp", "--json"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["title"] == "JSON Spec"


def test_plan_init_cli_creates_file(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "plan", "init",
            "--epic", "projects/demo_app/mvp",
            "--title", "CLI Plan",
            "--author", "alice",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    plans_dir = repo / "projects" / "demo_app" / "mvp" / "docs" / "plans"
    assert any(plans_dir.glob("*.md"))


def test_plan_list_cli_shows_plans(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    CliRunner().invoke(cli, ["plan", "init", "--epic", "projects/demo_app/mvp",
                            "--title", "Listed Plan", "--author", "alice"], obj={"cwd": repo})

    result = CliRunner().invoke(
        cli,
        ["plan", "list", "--epic", "projects/demo_app/mvp"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "Listed Plan" in result.output


def test_plan_spec_set_status_cli(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    spec_path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Status CLI", author="alice")
    spec_ref = str(spec_path.relative_to(repo))

    result = CliRunner().invoke(
        cli,
        ["plan", "spec", "set-status", spec_ref, "--status", "approved-for-spec", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    fm, _ = read_entity(spec_path)
    assert fm["status"] == "approved-for-spec"


def test_plan_set_status_cli(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    plan_path = create_plan(repo, epic_ref="projects/demo_app/mvp", title="Plan Status CLI", author="alice")
    plan_ref = str(plan_path.relative_to(repo))

    result = CliRunner().invoke(
        cli,
        ["plan", "set-status", plan_ref, "--status", "approved", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    fm, _ = read_entity(plan_path)
    assert fm["status"] == "approved"


def test_plan_link_spec_cli(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    spec_path = create_spec(repo, epic_ref="projects/demo_app/mvp", title="Link CLI Spec", author="alice")
    plan_path = create_plan(repo, epic_ref="projects/demo_app/mvp", title="Link CLI Plan", author="alice")

    result = CliRunner().invoke(
        cli,
        [
            "plan", "link-spec",
            "--plan", str(plan_path.relative_to(repo)),
            "--spec", str(spec_path.relative_to(repo)),
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    plan_fm, _ = read_entity(plan_path)
    assert plan_fm["linked_spec"] is not None


def test_plan_spec_init_missing_epic_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["plan", "spec", "init", "--epic", "projects/demo_app/missing", "--title", "X", "--author", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_plan_spec_init_unknown_author_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["plan", "spec", "init", "--epic", "projects/demo_app/mvp", "--title", "X", "--author", "unknown@example.com"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "not registered" in result.output
    assert "Traceback" not in result.output
