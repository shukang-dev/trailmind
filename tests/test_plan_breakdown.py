import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.pickup import build_task_pickup, log_task_pickup
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


def test_breakdown_write_creates_tasks_with_source_traceability(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    assert report.write is True
    assert report.created == [
        "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md",
        "projects/demo_app/mvp/tasks/T-123456-002-cli-wiring.md",
    ]
    assert [item.action for item in report.tasks] == ["created", "created"]
    first_path = repo / report.created[0]
    frontmatter, body = read_entity(first_path)
    assert frontmatter["id"] == "T-123456-001"
    assert frontmatter["title"] == "Parser Model"
    assert frontmatter["filer"] == "alice"
    assert frontmatter["owner"] == "alice"
    assert frontmatter["status"] == "created"
    assert frontmatter["source_plan"] == "docs/plans/v0.4.md"
    assert frontmatter["source_task"] == 1
    assert frontmatter["source_heading"] == "Task 1: Parser Model"
    assert frontmatter["code_paths"] == [
        "src/trailmind/plan_breakdown.py",
        "src/trailmind/cli.py",
        "tests/test_plan_breakdown.py",
    ]
    assert frontmatter["deliverables"] == ["tests pass", "plan task implemented"]
    assert "## Scope" in body
    assert "Implement Task 1 from `docs/plans/v0.4.md`." in body
    assert "Source heading: Task 1: Parser Model" in body
    assert "## Plan Steps" in body
    assert "- [ ] Step 1: Write the failing test" in body
    assert "## Source Context" in body
    assert "Expected: FAIL." in body
    assert "## Acceptance" in body
    assert "- Generated task is implemented." in body
    assert "## Activity Log" in body
    assert "Created task by alice." in body


def test_breakdown_write_skips_existing_source_task_by_default(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    first = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )
    second = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    assert len(first.created) == 2
    assert second.created == []
    assert second.skipped == first.created
    assert len(list((repo / "projects" / "demo_app" / "mvp" / "tasks").glob("T-*.md"))) == 2


def test_breakdown_write_force_creates_duplicate_source_task(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    forced = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=True,
    )

    assert forced.created == [
        "projects/demo_app/mvp/tasks/T-123456-003-parser-model.md",
        "projects/demo_app/mvp/tasks/T-123456-004-cli-wiring.md",
    ]


def test_generated_tasks_can_be_used_by_task_pickup(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    pack = build_task_pickup(repo, task_ref=report.created[0], max_lines=10, activity_limit=5, include_excerpts=False)

    assert pack.item["id"] == "T-123456-001"
    assert pack.item["frontmatter"]["code_paths"] == [
        "src/trailmind/plan_breakdown.py",
        "src/trailmind/cli.py",
        "tests/test_plan_breakdown.py",
    ]
    assert "Task is ready to start." in pack.next_actions


def test_breakdown_write_quotes_source_context_so_embedded_sections_do_not_hijack_pickup(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(
        repo,
        """# Demo Implementation Plan

### Task 1: Section Isolation

**Files:**
- Modify: `src/trailmind/plan_breakdown.py`

## Acceptance

- Source acceptance must not become task acceptance.

## Activity Log

- 2026-01-01: Source context activity.

```python
print("source fence")
```
""",
    )
    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )
    task_path = repo / report.created[0]
    _frontmatter, body = read_entity(task_path)

    assert "````\n> **Files:**" in body
    assert "> ```python" in body
    assert "> ## Acceptance" in body
    assert "> ## Activity Log" in body
    pack = build_task_pickup(repo, task_ref=report.created[0], max_lines=10, activity_limit=5, include_excerpts=False)
    assert pack.item["acceptance"] == "- Generated task is implemented.\n- Relevant tests pass."
    assert len(pack.activity) == 1
    assert "Created task by alice." in pack.activity[0]
    assert "Source context activity" not in "\n".join(pack.activity)

    log_task_pickup(repo, task_ref=report.created[0], actor="alice", output_format="markdown")

    updated = build_task_pickup(repo, task_ref=report.created[0], max_lines=10, activity_limit=5, include_excerpts=False)
    assert len(updated.activity) == 2
    assert "Created task by alice." in updated.activity[0]
    assert "Picked up for handoff by alice." in updated.activity[1]
    assert "Source context activity" not in "\n".join(updated.activity)


def test_breakdown_write_skips_duplicate_source_task_number_in_same_plan(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(
        repo,
        """# Demo Implementation Plan

### Task 1: Parser Model

**Files:**
- Modify: `src/trailmind/plan_breakdown.py`

### Task 1: Parser Followup

**Files:**
- Modify: `tests/test_plan_breakdown.py`
""",
    )

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    assert report.created == ["projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"]
    assert report.skipped == ["projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"]
    assert [item.action for item in report.tasks] == ["created", "skip"]
    assert report.tasks[1].existing_path == "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"
    assert len(list((repo / "projects" / "demo_app" / "mvp" / "tasks").glob("T-*.md"))) == 1


def test_breakdown_preview_skips_duplicate_source_task_number_in_same_plan_without_writing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(
        repo,
        """# Demo Implementation Plan

### Task 1: Parser Model

**Files:**
- Modify: `src/trailmind/plan_breakdown.py`

### Task 1: Parser Followup

**Files:**
- Modify: `tests/test_plan_breakdown.py`
""",
    )
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=False,
        force=False,
    )

    first_would_be_path = "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md"
    assert report.created == []
    assert report.skipped == [first_would_be_path]
    assert [item.action for item in report.tasks] == ["create", "skip"]
    assert report.tasks[0].existing_path is None
    assert report.tasks[1].existing_path == first_would_be_path
    assert not list(tasks_path.glob("T-*.md"))


def test_breakdown_write_force_allows_duplicate_source_task_number_in_same_plan(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(
        repo,
        """# Demo Implementation Plan

### Task 1: Parser Model

**Files:**
- Modify: `src/trailmind/plan_breakdown.py`

### Task 1: Parser Followup

**Files:**
- Modify: `tests/test_plan_breakdown.py`
""",
    )

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=True,
    )

    assert report.created == [
        "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md",
        "projects/demo_app/mvp/tasks/T-123456-002-parser-followup.md",
    ]
    assert report.skipped == []
    assert [item.action for item in report.tasks] == ["created", "created"]


def test_plan_breakdown_cli_preview_prints_markdown_without_writing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "# Plan Breakdown Preview" in result.output
    assert "Task 1: Parser Model [create]" in result.output
    assert not list((repo / "projects" / "demo_app" / "mvp" / "tasks").glob("T-*.md"))


def test_plan_breakdown_cli_preview_prints_json(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice",
            "--owner",
            "alice",
            "--json",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["write"] is False
    assert data["tasks"][0]["source_heading"] == "Task 1: Parser Model"


def test_plan_breakdown_cli_write_creates_tasks(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--write",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "# Plan Breakdown Write" in result.output
    assert "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md" in result.output
    assert (repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-parser-model.md").exists()


def test_plan_breakdown_cli_json_write_lists_created_paths(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--write",
            "--json",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["write"] is True
    assert data["created"] == [
        "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md",
        "projects/demo_app/mvp/tasks/T-123456-002-cli-wiring.md",
    ]


def test_plan_breakdown_missing_plan_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/missing.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "plan path 'docs/plans/missing.md' not found" in result.output
    assert "Traceback" not in result.output


def test_plan_breakdown_unknown_owner_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "missing@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "missing@example.com is not registered in roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_plan_breakdown_rejects_unsafe_plan_path_without_writing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "../outside.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "path escapes repository: ../outside.md" in result.output
    assert "Traceback" not in result.output


def test_plan_breakdown_rejects_non_markdown_plan(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = repo / "docs" / "plans" / "v0.4.txt"
    path.parent.mkdir(parents=True)
    path.write_text(PLAN_TEXT, encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.txt",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "plan path must be a Markdown file" in result.output


def test_plan_breakdown_rejects_non_utf8_plan(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    path = repo / "docs" / "plans" / "bad.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/bad.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "file is not UTF-8" in result.output


def test_plan_breakdown_rejects_missing_epic(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/missing",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "epic projects/demo_app/missing does not exist" in result.output


def test_plan_breakdown_rejects_non_standard_in_repo_epic_path(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    scratch_epic = repo / "scratch" / "demo" / "mvp"
    scratch_epic.mkdir(parents=True)
    (scratch_epic / "EPIC.md").write_text("# Scratch MVP\n", encoding="utf-8")

    with pytest.raises(TrailmindError, match="epic scratch/demo/mvp does not exist"):
        build_breakdown_report(
            repo,
            plan_ref="docs/plans/v0.4.md",
            epic_ref="scratch/demo/mvp",
            filer="alice@example.com",
            owner="alice@example.com",
            write=False,
            force=False,
        )


def test_plan_breakdown_rejects_unsafe_epic_path(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "../mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "path escapes repository: ../mvp" in result.output


def test_plan_breakdown_rejects_tasks_path_that_is_file(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    for child in tasks_path.iterdir():
        child.unlink()
    tasks_path.rmdir()
    tasks_path.write_text("not a directory", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--write",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "tasks path" in result.output
    assert "is not a directory" in result.output


def test_plan_breakdown_write_rejects_symlinked_tasks_path_that_escapes_repo(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    outside_tasks = tmp_path.parent / f"{tmp_path.name}_outside_tasks"
    outside_tasks.mkdir()
    tasks_path.rmdir()
    tasks_path.symlink_to(outside_tasks, target_is_directory=True)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--write",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "tasks path" in result.output
    assert "escapes repository" in result.output
    assert not list(outside_tasks.glob("T-*.md"))


def test_plan_breakdown_rejects_unknown_filer(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _write_plan(repo)

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "breakdown",
            "docs/plans/v0.4.md",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "missing@example.com",
            "--owner",
            "alice@example.com",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "missing@example.com is not registered in roster.yaml" in result.output


# --- Task 5: Plan Breakdown Integration — generated_tasks ---

def test_breakdown_write_updates_plan_generated_tasks(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    plan_path = _write_plan(repo)

    report = build_breakdown_report(
        repo,
        plan_ref="docs/plans/v0.4.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    plan_text = plan_path.read_text(encoding="utf-8")
    from trailmind.plan_artifact import parse_plan_info
    info = parse_plan_info(plan_text, path="docs/plans/v0.4.md")

    assert len(info.generated_tasks) == 2
    assert "T-123456-001" in info.generated_tasks
    assert "T-123456-002" in info.generated_tasks
    assert report.created == [
        "projects/demo_app/mvp/tasks/T-123456-001-parser-model.md",
        "projects/demo_app/mvp/tasks/T-123456-002-cli-wiring.md",
    ]


def test_breakdown_write_legacy_plan_gets_minimal_frontmatter(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    # Write a plan WITHOUT frontmatter
    legacy_plan = repo / "projects" / "demo_app" / "mvp" / "docs" / "plans" / "legacy.md"
    legacy_plan.parent.mkdir(parents=True, exist_ok=True)
    legacy_plan.write_text(PLAN_TEXT, encoding="utf-8")

    report = build_breakdown_report(
        repo,
        plan_ref="projects/demo_app/mvp/docs/plans/legacy.md",
        epic_ref="projects/demo_app/mvp",
        filer="alice@example.com",
        owner="alice@example.com",
        write=True,
        force=False,
    )

    assert len(report.created) == 2
    updated = legacy_plan.read_text(encoding="utf-8")
    assert "---" in updated
    assert "generated_tasks" in updated
