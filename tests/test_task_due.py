from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_task(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id


def test_task_due_set(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "due", task_id, "2026-07-15", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["due"] == "2026-07-15"
    assert "Due date set to 2026-07-15" in body


def test_task_due_clear(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()

    # Set first
    runner.invoke(cli, ["task", "due", task_id, "2026-07-15", "--actor", "alice"], obj={"cwd": repo})

    # Clear
    result = runner.invoke(cli, ["task", "due", task_id, "--clear", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["due"] is None
    assert "Cleared due date" in body


def test_task_due_with_note(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "due", task_id, "2026-08-01", "--actor", "alice", "--note", "Hard deadline"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["due"] == "2026-08-01"
    assert "Hard deadline" in body


def test_task_due_invalid_date(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "due", task_id, "not-a-date", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid due date" in result.output
    assert "Traceback" not in result.output


def test_task_due_missing_date(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "due", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "due date is required" in result.output
