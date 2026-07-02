import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.plan_breakdown import (
    breakdown_report_to_dict,
    build_breakdown_report,
    derive_code_paths,
    derive_deliverables,
    format_breakdown_markdown,
    parse_plan_tasks,
)


PLAN_TEXT = """# Demo Implementation Plan

Intro text.

### Task 1: Parser Model

**Files:**
- Create: `src/trailmind/plan_breakdown.py`
- Modify: `src/trailmind/cli.py:40-60`
- Test: `tests/test_plan_breakdown.py`
- Note: review manually

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run the test**

Run:

```bash
/Users/example/IdeaProjects/trailmind/.venv/bin/python -m pytest tests/test_plan_breakdown.py::test_parser -v
```

Expected: FAIL.

```bash
git commit -m "feat: add plan parser"
```

### Task 2: CLI Wiring

**Files:**
- Modify: `src/trailmind/cli.py`

- [ ] **Step 1: Add command tests**
"""


def test_parse_plan_tasks_extracts_supported_task_sections():
    tasks = parse_plan_tasks(PLAN_TEXT)

    assert len(tasks) == 2
    first = tasks[0]
    assert first.source_task == 1
    assert first.source_heading == "Task 1: Parser Model"
    assert first.title == "Parser Model"
    assert first.file_entries == [
        ("Create", "src/trailmind/plan_breakdown.py"),
        ("Modify", "src/trailmind/cli.py:40-60"),
        ("Test", "tests/test_plan_breakdown.py"),
        ("Note", "review manually"),
    ]
    assert first.steps == ["Step 1: Write the failing test", "Step 2: Run the test"]
    assert first.verification_commands == [
        "/Users/example/IdeaProjects/trailmind/.venv/bin/python -m pytest tests/test_plan_breakdown.py::test_parser -v"
    ]
    assert first.commit_message == "feat: add plan parser"
    assert "Expected: FAIL." in first.source_context


def test_parse_plan_tasks_rejects_plan_without_supported_sections():
    with pytest.raises(TrailmindError, match="plan contains no supported task sections"):
        parse_plan_tasks("# Plan\n\n## Task 1\n\nWrong heading level.\n")


def test_parse_plan_tasks_rejects_malformed_task_heading():
    text = "# Plan\n\n### Task: Missing number\n\nBody.\n"

    with pytest.raises(TrailmindError, match="malformed task heading"):
        parse_plan_tasks(text)


def test_parse_plan_tasks_ignores_task_headings_inside_fenced_code_blocks():
    tasks = parse_plan_tasks(
        "# Plan\n\n"
        "### Task 1: Real Parser Task\n\n"
        "Example:\n\n"
        "```markdown\n"
        "### Task 2: Fixture Only\n"
        "```\n"
    )

    assert len(tasks) == 1
    assert tasks[0].source_task == 1
    assert tasks[0].title == "Real Parser Task"


def test_parse_plan_tasks_ignores_malformed_task_headings_inside_fenced_code_blocks():
    tasks = parse_plan_tasks(
        "# Plan\n\n"
        "### Task 1: Real Parser Task\n\n"
        "Example:\n\n"
        "```\n"
        "### Task: Missing number\n"
        "```\n"
    )

    assert len(tasks) == 1
    assert tasks[0].title == "Real Parser Task"


def test_parse_plan_tasks_rejects_task_heading_without_same_line_title():
    text = "# Plan\n\n### Task 2:\nMissing title\n"

    with pytest.raises(TrailmindError, match="malformed task heading"):
        parse_plan_tasks(text)


def test_parse_plan_tasks_extracts_multiple_verification_commands_from_fenced_run_block():
    tasks = parse_plan_tasks(
        "### Task 1: Verify Multiple Commands\n\n"
        "Run:\n\n"
        "```bash\n"
        "python -m pytest tests/test_plan_breakdown.py -v\n"
        "\n"
        "python -m pytest -q\n"
        "```\n"
    )

    assert tasks[0].verification_commands == [
        "python -m pytest tests/test_plan_breakdown.py -v",
        "python -m pytest -q",
    ]


def test_derive_code_paths_from_file_entries():
    tasks = parse_plan_tasks(PLAN_TEXT)

    assert derive_code_paths(tasks[0]) == [
        "src/trailmind/plan_breakdown.py",
        "src/trailmind/cli.py",
        "tests/test_plan_breakdown.py",
    ]


def test_derive_deliverables_adds_docs_only_when_docs_are_mentioned():
    parser_task = parse_plan_tasks(PLAN_TEXT)[0]
    docs_task = parse_plan_tasks(
        "### Task 1: Public Docs\n\n"
        "**Files:**\n"
        "- Create: `docs/v0.4-plan-breakdown.md`\n"
        "\n"
        "- [ ] **Step 1: Write docs**\n"
    )[0]

    assert derive_deliverables(parser_task) == ["tests pass", "plan task implemented"]
    assert derive_deliverables(docs_task) == ["tests pass", "plan task implemented", "docs updated"]


def _repo_with_epic(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n"
        "  shortname: alice\n"
        "  uid: '123456'\n"
        "  name: Alice\n",
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
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "mvp",
            "--title",
            "MVP",
            "--goal",
            "First usable release",
            "--roster",
            "alice",
            "--repos",
            "demo_app",
        ],
        obj={"cwd": tmp_path},
    ).exit_code == 0
    return tmp_path


def _write_plan(repo: Path, text: str = PLAN_TEXT) -> Path:
    path = repo / "docs" / "plans" / "v0.4.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_build_breakdown_report_preview_is_read_only(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    before = sorted(tasks_path.glob("*.md"))

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice",
        owner="alice",
        write=False,
        force=False,
    )

    assert [item.action for item in report.tasks] == ["create", "create"]
    assert report.created == []
    assert report.skipped == []
    assert sorted(tasks_path.glob("*.md")) == before
    rendered = format_breakdown_markdown(report)
    assert "# Plan Breakdown Preview" in rendered
    assert "Task 1: Parser Model" in rendered
    assert "create" in rendered


def test_breakdown_report_to_dict_shape(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice",
        owner="alice",
        write=False,
        force=False,
    )
    data = breakdown_report_to_dict(report)

    assert data["plan_path"] == "docs/plans/v0.4.md"
    assert data["epic_path"] == "projects/demo_app/mvp"
    assert data["write"] is False
    assert data["force"] is False
    assert data["tasks"][0]["source_task"] == 1
    assert data["tasks"][0]["action"] == "create"
    assert data["tasks"][0]["existing_path"] is None
    assert data["created"] == []
    assert data["skipped"] == []
    json.dumps(data)


def test_duplicate_detection_skips_existing_source_task(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    existing = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-parser-model.md"
    write_entity(
        existing,
        frontmatter={
            "id": "T-123456-001",
            "title": "Parser Model",
            "filer": "alice",
            "owner": "alice",
            "status": "created",
            "created": "2026-07-02",
            "start": None,
            "due": None,
            "branches": {},
            "verify": {},
            "code_paths": [],
            "design_doc": None,
            "depends_on": [],
            "soft_depends_on": [],
            "known_issues": [],
            "deliverables": [],
            "completed_deliverables": [],
            "source_plan": "docs/plans/v0.4.md",
            "source_task": 1,
            "source_heading": "Task 1: Parser Model",
        },
        body="# Parser Model\n\n## Scope\n\nExisting.\n",
    )
    frontmatter, _body = read_entity(existing)
    assert frontmatter["source_task"] == 1

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice",
        owner="alice",
        write=False,
        force=False,
    )

    assert report.tasks[0].action == "skip"
    assert report.tasks[0].existing_path == "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"
    assert report.skipped == ["projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"]


def test_duplicate_detection_skips_existing_source_task_stored_as_string(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    existing = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-parser-model.md"
    write_entity(
        existing,
        frontmatter={
            "id": "T-123456-001",
            "title": "Parser Model",
            "filer": "alice",
            "owner": "alice",
            "status": "created",
            "created": "2026-07-02",
            "start": None,
            "due": None,
            "branches": {},
            "verify": {},
            "code_paths": [],
            "design_doc": None,
            "depends_on": [],
            "soft_depends_on": [],
            "known_issues": [],
            "deliverables": [],
            "completed_deliverables": [],
            "source_plan": "docs/plans/v0.4.md",
            "source_task": "1",
            "source_heading": "Task 1: Parser Model",
        },
        body="# Parser Model\n\n## Scope\n\nExisting.\n",
    )
    frontmatter, _body = read_entity(existing)
    assert frontmatter["source_task"] == "1"

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice",
        owner="alice",
        write=False,
        force=False,
    )

    assert report.tasks[0].action == "skip"
    assert report.tasks[0].existing_path == "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"
    assert report.skipped == ["projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"]


def test_force_marks_duplicate_for_creation(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    existing = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-parser-model.md"
    write_entity(
        existing,
        frontmatter={
            "id": "T-123456-001",
            "title": "Parser Model",
            "filer": "alice",
            "owner": "alice",
            "status": "created",
            "created": "2026-07-02",
            "start": None,
            "due": None,
            "branches": {},
            "verify": {},
            "code_paths": [],
            "design_doc": None,
            "depends_on": [],
            "soft_depends_on": [],
            "known_issues": [],
            "deliverables": [],
            "completed_deliverables": [],
            "source_plan": "docs/plans/v0.4.md",
            "source_task": 1,
            "source_heading": "Task 1: Parser Model",
        },
        body="# Parser Model\n\n## Scope\n\nExisting.\n",
    )

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=False,
        force=True,
    )

    assert report.tasks[0].action == "duplicate allowed by --force"
    assert report.tasks[0].existing_path == "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"
