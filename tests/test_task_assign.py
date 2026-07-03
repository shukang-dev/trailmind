from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_two_users(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: bob@example.com\n  shortname: bob\n  uid: '654321'\n  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice,bob", "--repos", "demo"], obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id


def test_task_assign_changes_owner(tmp_path: Path):
    repo, task_id = _repo_with_two_users(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "assign", task_id, "bob@example.com", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["owner"] == "bob"
    assert "Assigned to bob" in body
    assert "was alice" in body


def test_task_assign_with_shortname(tmp_path: Path):
    repo, task_id = _repo_with_two_users(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "assign", task_id, "bob", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["owner"] == "bob"


def test_task_assign_with_note(tmp_path: Path):
    repo, task_id = _repo_with_two_users(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "assign", task_id, "bob@example.com", "--actor", "alice", "--note", "Bob has more bandwidth"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    _fm, body = read_entity(task_file)
    assert "Bob has more bandwidth" in body


def test_task_assign_unknown_user_is_error(tmp_path: Path):
    repo, task_id = _repo_with_two_users(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "assign", task_id, "charlie@example.com", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
