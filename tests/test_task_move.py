from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_two_epics(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Create a repo with two epics and one task in the first epic. Returns (repo, task_id, epic_a_path, epic_b_path)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "epic_a", "--title", "Epic A",
                        "--goal", "First epic.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "epic_b", "--title", "Epic B",
                        "--goal", "Second epic.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/epic_a", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Movable Task", "--priority", "high"],
                  obj={"cwd": tmp_path})

    task_files = sorted((tmp_path / "projects" / "demo" / "epic_a" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id, "projects/demo/epic_a", "projects/demo/epic_b"


def test_task_move(tmp_path: Path):
    repo, task_id, epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()

    # Verify task is in epic_a
    assert (repo / "projects" / "demo" / "epic_a" / "tasks").glob("T-*movable-task.md")

    result = runner.invoke(cli, ["task", "move", task_id, epic_b, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    # Verify task moved to epic_b
    task_files_b = list((repo / "projects" / "demo" / "epic_b" / "tasks").glob("T-*movable-task.md"))
    assert len(task_files_b) == 1

    # Verify task no longer in epic_a
    task_files_a = list((repo / "projects" / "demo" / "epic_a" / "tasks").glob("T-*movable-task.md"))
    assert len(task_files_a) == 0

    # Verify activity log
    fm, body = read_entity(task_files_b[0])
    assert "Moved" in body
    assert epic_a in body
    assert epic_b in body


def test_task_move_same_epic_is_error(tmp_path: Path):
    repo, task_id, epic_a, _epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "move", task_id, epic_a, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code != 0
    assert "already" in result.output


def test_task_move_preserves_metadata(tmp_path: Path):
    repo, task_id, _epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "move", task_id, epic_b, "--actor", "alice", "--note", "Reorganizing"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_files_b = list((repo / "projects" / "demo" / "epic_b" / "tasks").glob("T-*movable-task.md"))
    fm, body = read_entity(task_files_b[0])
    assert fm["title"] == "Movable Task"
    assert fm["priority"] == "high"
    assert "Reorganizing" in body


def test_task_move_can_list_from_target(tmp_path: Path):
    repo, task_id, _epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["task", "move", task_id, epic_b, "--actor", "alice"], obj={"cwd": repo})

    result = runner.invoke(cli, ["task", "list", "--epic", epic_b], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Movable Task" in result.output
