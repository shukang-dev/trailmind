import pytest

from trailmind.errors import TrailmindError
from trailmind.plan_breakdown import (
    derive_code_paths,
    derive_deliverables,
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
