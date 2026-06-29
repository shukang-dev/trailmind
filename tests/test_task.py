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


def _add_task(repo: Path, title: str = "Build Login Flow"):
    return CliRunner().invoke(
        cli,
        [
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
        ],
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
    assert frontmatter["filer"] == "alice"
    assert frontmatter["owner"] == "alice"
    assert frontmatter["status"] == "planned"
    assert frontmatter["code_paths"] == ["src/app.py", "tests/test_app.py"]
    assert frontmatter["depends_on"] == []
    assert frontmatter["soft_depends_on"] == []
    assert "## Scope" in body
    assert "## Acceptance" in body
    assert "## Activity Log" in body


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
