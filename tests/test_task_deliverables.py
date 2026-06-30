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


def test_task_add_accepts_deliverables(tmp_path: Path):
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
            "alice@example.com",
            "--title",
            "Build parser",
            "--deliverables",
            "tests pass, docs updated",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-parser.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["deliverables"] == ["tests pass", "docs updated"]
    assert frontmatter["completed_deliverables"] == []


def test_task_add_normalizes_deliverables_for_completion(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    add_result = CliRunner().invoke(
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
            "Build parser",
            "--deliverables",
            "tests  pass",
        ],
        obj={"cwd": repo},
    )
    assert add_result.exit_code == 0

    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-parser.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["deliverables"] == ["tests pass"]

    progress = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert progress.exit_code == 0

    complete = CliRunner().invoke(
        cli,
        ["task", "deliverable", "complete", "T-123456-001", "--item", "tests pass", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert complete.exit_code == 0

    frontmatter, _body = read_entity(task_path)
    assert frontmatter["completed_deliverables"] == ["tests pass"]


def test_task_close_requires_completed_deliverables(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = CliRunner().invoke(
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
            "Build parser",
            "--deliverables",
            "tests pass, docs updated",
        ],
        obj={"cwd": repo},
    )
    assert add_result.exit_code == 0

    progress = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert progress.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "missing completed deliverables" in blocked.output
    assert "tests pass" in blocked.output
    assert "docs updated" in blocked.output

    for item in ["tests pass", "docs updated"]:
        complete = CliRunner().invoke(
            cli,
            ["task", "deliverable", "complete", "T-123456-001", "--item", item, "--actor", "alice"],
            obj={"cwd": repo},
        )
        assert complete.exit_code == 0

    closed = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert closed.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-parser.md"
    frontmatter, body = read_entity(task_path)
    assert frontmatter["status"] == "done"
    assert frontmatter["completed_deliverables"] == ["tests pass", "docs updated"]
    assert "Completed deliverable by alice. tests pass" in body


def test_task_set_status_done_requires_completed_deliverables(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = CliRunner().invoke(
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
            "Build parser",
            "--deliverables",
            "tests pass",
        ],
        obj={"cwd": repo},
    )
    assert add_result.exit_code == 0

    progress = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert progress.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "done", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "missing completed deliverables" in blocked.output
    assert "tests pass" in blocked.output
    assert "Traceback" not in blocked.output


def test_task_deliverable_add_rejects_done_task(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = CliRunner().invoke(
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
            "Build parser",
            "--deliverables",
            "tests pass",
        ],
        obj={"cwd": repo},
    )
    assert add_result.exit_code == 0

    progress = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert progress.exit_code == 0

    complete = CliRunner().invoke(
        cli,
        ["task", "deliverable", "complete", "T-123456-001", "--item", "tests pass", "--actor", "alice"],
        obj={"cwd": repo},
    )
    assert complete.exit_code == 0

    closed = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
        obj={"cwd": repo},
    )
    assert closed.exit_code == 0

    blocked = CliRunner().invoke(
        cli,
        ["task", "deliverable", "add", "T-123456-001", "--item", "docs updated", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert blocked.exit_code == 1
    assert "cannot add deliverable to done task" in blocked.output
    assert "Traceback" not in blocked.output

    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-parser.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["deliverables"] == ["tests pass"]
