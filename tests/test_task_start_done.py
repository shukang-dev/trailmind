from datetime import date
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


def test_task_start_sets_in_progress(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "start", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["status"] == "in_progress"
    assert "Status changed from created to in_progress" in body


def test_task_start_sets_start_date(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "start", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["start"] == date.today().isoformat()


def test_task_start_with_note(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "start", task_id, "--actor", "alice", "--note", "Starting work"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    _fm, body = read_entity(task_file)
    assert "Starting work" in body


def test_task_done_sets_done(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()

    # Start first
    runner.invoke(cli, ["task", "start", task_id, "--actor", "alice"], obj={"cwd": repo})

    # Then done
    result = runner.invoke(cli, ["task", "done", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["status"] == "done"
    assert "Status changed from in_progress to done" in body


def test_task_done_with_note(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "done", task_id, "--actor", "alice", "--note", "All tests pass"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    _fm, body = read_entity(task_file)
    assert "All tests pass" in body


def test_task_done_from_created(tmp_path: Path):
    """Can mark a task done directly from created."""
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "done", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["status"] == "done"
