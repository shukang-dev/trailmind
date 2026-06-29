from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.task import split_csv


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
    epic = tmp_path / "projects" / "demo_app" / "mvp"
    (epic / "tasks").mkdir(parents=True)
    (epic / "EPIC.md").write_text(
        "---\n"
        "slug: mvp\n"
        "title: MVP\n"
        "project: demo_app\n"
        "---\n"
        "# MVP\n",
        encoding="utf-8",
    )
    return tmp_path


def _add_task(repo: Path, title: str = "Build Login Flow", extra_args: list[str] | None = None):
    args = [
        "task",
        "add",
        "--epic",
        "projects/demo_app/mvp",
        "--filer",
        "alice@example.com",
        "--owner",
        "alice@example.com",
        "--title",
        title,
        "--code-paths",
        "src/app.py, tests/test_app.py",
        "--depends-on",
        "",
        "--soft-depends-on",
        " , ",
    ]
    if extra_args:
        args.extend(extra_args)
    return CliRunner().invoke(
        cli,
        args,
        obj={"cwd": repo},
    )


def test_task_add_creates_task(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = _add_task(repo)

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output

    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    assert task_path.exists()

    frontmatter, body = read_entity(task_path)
    assert frontmatter["id"] == "T-123456-001"
    assert frontmatter["title"] == "Build Login Flow"
    assert frontmatter["filer"] == "alice"
    assert frontmatter["owner"] == "alice"
    assert frontmatter["status"] == "planned"
    assert date.fromisoformat(frontmatter["created"])
    assert frontmatter["start"] is None
    assert frontmatter["due"] is None
    assert frontmatter["branches"] == {}
    assert frontmatter["verify"] == {}
    assert frontmatter["code_paths"] == ["src/app.py", "tests/test_app.py"]
    assert frontmatter["design_doc"] is None
    assert frontmatter["depends_on"] == []
    assert frontmatter["soft_depends_on"] == []
    assert frontmatter["known_issues"] == []
    assert "## Scope" in body
    assert "## Acceptance" in body
    assert "## Activity Log" in body


def test_task_add_writes_design_doc_when_specified(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = _add_task(repo, extra_args=["--design-doc", "docs/specs/parser.md"])

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["design_doc"] == "docs/specs/parser.md"


def test_task_update_status(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "update", "T-123456-001", "--status", "in_progress"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["status"] == "in_progress"


@pytest.mark.parametrize(
    "args",
    [
        ["task", "update", "T-123456-001", "--status", "done"],
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
    ],
)
def test_task_status_commands_handle_unreadable_task_files_as_user_errors(tmp_path: Path, args: list[str]):
    repo = _repo_with_epic(tmp_path)
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-bad.md"
    task_path.write_bytes(b"\xff\xfe\x00not utf-8")

    result = CliRunner().invoke(
        cli,
        args,
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.output
    assert "could not read task file" in result.output
    assert "Traceback" not in result.output


def test_task_close_marks_done_and_logs(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Shipped login flow."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    assert frontmatter["status"] == "done"
    assert "Shipped login flow." in body
    assert body.index("## Activity Log") < body.index("Shipped login flow.")


def test_task_close_sanitizes_multiline_note_before_logging(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "done\n## Injected\ntext"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert result.exception is None
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    _frontmatter, body = read_entity(task_path)
    activity_line = next(line for line in body.splitlines() if "Closed by alice" in line)
    assert activity_line.endswith("done ## Injected text")
    assert "\n## Injected\n" not in body


def test_task_close_sanitizes_multiline_closer_before_logging(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice\n## Injected", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert result.exception is None
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    _frontmatter, body = read_entity(task_path)
    activity_lines = [
        line
        for line in body.splitlines()[body.splitlines().index("## Activity Log") + 1 :]
        if line.strip()
    ]
    closed_lines = [line for line in activity_lines if "Closed by alice ## Injected" in line]
    assert closed_lines == [f"- {date.today().isoformat()}: Closed by alice ## Injected. Done."]
    assert all(line.startswith("- ") for line in activity_lines)
    assert "\n## Injected" not in body


def test_task_close_rejects_blank_closer(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", " \n\t", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "activity actor is required" in result.output
    assert "Traceback" not in result.output


def test_task_update_invalid_status_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "update", "T-123456-001", "--status", "bogus"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid task status" in result.output
    assert "Traceback" not in result.output


def test_task_add_unknown_filer_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "missing@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "missing@example.com is not registered in roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_task_add_when_tasks_path_is_file_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    tasks_path.rmdir()
    tasks_path.write_text("not a directory\n", encoding="utf-8")

    result = _add_task(repo)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.output
    assert "tasks path" in result.output
    assert "not a directory" in result.output
    assert "Traceback" not in result.output


def test_task_add_unknown_owner_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "missing@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "missing@example.com is not registered in roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_task_add_missing_epic_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/missing",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "epic projects/demo_app/missing does not exist" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        (" , ", []),
        ("src/app.py, tests/test_app.py", ["src/app.py", "tests/test_app.py"]),
        (" first , second ,, third ", ["first", "second", "third"]),
    ],
)
def test_split_csv_trims_and_drops_empty_entries(value: str, expected: list[str]):
    assert split_csv(value) == expected
