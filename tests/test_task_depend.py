from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_two_tasks(tmp_path: Path) -> tuple[Path, str, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing",
                        "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task A"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task B"], obj={"cwd": tmp_path})

    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_a_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    task_b_id = task_files[1].stem.split("-")[0] + "-" + task_files[1].stem.split("-")[1] + "-" + task_files[1].stem.split("-")[2]
    return tmp_path, task_a_id, task_b_id


def test_task_depend_add(tmp_path: Path):
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert task_b in fm["depends_on"]
    assert "Added dependency" in body


def test_task_depend_add_soft(tmp_path: Path):
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--soft", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert task_b in fm["soft_depends_on"]
    assert "soft dependency" in body


def test_task_depend_remove(tmp_path: Path):
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    # Add first
    runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    # Then remove
    result = runner.invoke(cli, ["task", "depend", "remove", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert task_b not in fm["depends_on"]
    assert "Removed dependency" in body


def test_task_depend_self_is_error(tmp_path: Path):
    repo, task_a, _task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "depend", "add", task_a, task_a, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "itself" in result.output


def test_task_depend_duplicate_is_error(tmp_path: Path):
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    result = runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "already has" in result.output


def test_task_depend_remove_nonexistent_is_error(tmp_path: Path):
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "depend", "remove", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "does not have" in result.output


def test_task_depend_blocks_status_transition(tmp_path: Path):
    """Adding a hard dependency should prevent marking the task as done if dep isn't done."""
    repo, task_a, task_b = _repo_with_two_tasks(repo := tmp_path)
    runner = CliRunner()
    # Add dependency: Task A depends on Task B
    runner.invoke(cli, ["task", "depend", "add", task_a, task_b, "--actor", "alice"], obj={"cwd": repo})
    # Set Task A to ready
    runner.invoke(cli, ["task", "set-status", task_a, "ready", "--actor", "alice"], obj={"cwd": repo})
    # Try to mark Task A as done — should fail because Task B is not done
    result = runner.invoke(cli, ["task", "done", task_a, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
