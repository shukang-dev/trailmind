from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity


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


def _task_path(repo: Path, filename: str) -> Path:
    return repo / "projects" / "demo_app" / "mvp" / "tasks" / filename


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


def test_missing_hard_dependency_blocks_ready_and_leaves_status_unchanged(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    result = _add_task(repo, "Build UI", ["--depends-on", "T-123456-999"])
    assert result.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "unsatisfied hard dependencies" in blocked.output
    assert "T-123456-999" in blocked.output
    frontmatter, _body = read_entity(_task_path(repo, "T-123456-001-build-ui.md"))
    assert frontmatter["status"] == "created"


def test_hard_dependency_blocks_in_progress(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--depends-on", "T-123456-001"])
    assert second.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "unsatisfied hard dependencies" in blocked.output
    assert "T-123456-001" in blocked.output


def test_hard_dependency_blocks_done_via_set_status(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--depends-on", "T-123456-001"])
    assert second.exit_code == 0
    task_path = _task_path(repo, "T-123456-002-build-ui.md")
    frontmatter, body = read_entity(task_path)
    frontmatter["status"] = "ready"
    write_entity(task_path, frontmatter=frontmatter, body=body)

    blocked = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "done", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "unsatisfied hard dependencies" in blocked.output
    assert "T-123456-001" in blocked.output
    reread_frontmatter, _body = read_entity(task_path)
    assert reread_frontmatter["status"] == "ready"


def test_task_close_enforces_hard_dependency_gate(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--depends-on", "T-123456-001"])
    assert second.exit_code == 0
    task_path = _task_path(repo, "T-123456-002-build-ui.md")
    frontmatter, body = read_entity(task_path)
    frontmatter["status"] = "in_progress"
    write_entity(task_path, frontmatter=frontmatter, body=body)

    blocked = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-002", "--closer", "alice", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "unsatisfied hard dependencies" in blocked.output
    assert "T-123456-001" in blocked.output
    reread_frontmatter, _body = read_entity(task_path)
    assert reread_frontmatter["status"] == "in_progress"


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


def test_missing_soft_dependency_warns_without_blocking_status_transition(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    result = _add_task(repo, "Build UI", ["--soft-depends-on", "T-123456-999"])
    assert result.exit_code == 0

    ready = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert ready.exit_code == 0
    assert "soft dependencies are not terminal" in ready.output
    assert "T-123456-999" in ready.output
    frontmatter, _body = read_entity(_task_path(repo, "T-123456-001-build-ui.md"))
    assert frontmatter["status"] == "ready"


def test_unreadable_soft_dependency_warns_without_blocking_status_transition(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first = _add_task(repo, "Build parser")
    assert first.exit_code == 0
    second = _add_task(repo, "Build UI", ["--soft-depends-on", "T-123456-001"])
    assert second.exit_code == 0
    _task_path(repo, "T-123456-001-build-parser.md").write_bytes(b"\xff\xfe\x00not utf-8")

    ready = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-002", "ready", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert ready.exit_code == 0
    assert "soft dependencies are not terminal" in ready.output
    assert "T-123456-001" in ready.output
    frontmatter, _body = read_entity(_task_path(repo, "T-123456-002-build-ui.md"))
    assert frontmatter["status"] == "ready"
