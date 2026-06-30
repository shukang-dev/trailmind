from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


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


def _add_task(repo: Path, title: str, extra_args: list[str] | None = None):
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
    ]
    if extra_args:
        args.extend(extra_args)
    return CliRunner().invoke(cli, args, obj={"cwd": repo})


def test_hard_dependency_blocks_ready_until_dependency_is_terminal(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--depends-on", "T-123456-001"])
    assert second.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "unsatisfied hard dependencies" in blocked.output
    assert "T-123456-001" in blocked.output

    move_first = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert move_first.exit_code == 0
    close_first = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Parser complete."],
        obj={"cwd": repo},
    )
    assert close_first.exit_code == 0

    ready = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert ready.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-002-build-ui.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["status"] == "ready"


def test_soft_dependency_does_not_block_status_transition(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--soft-depends-on", "T-123456-001"])
    assert second.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "soft dependencies are not terminal" in result.output
    assert "T-123456-001" in result.output
