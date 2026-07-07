from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_activity(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: bob@example.com\n  shortname: bob\n  uid: '654321'\n  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test Epic",
                        "--goal", "Testing", "--roster", "alice,bob", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    # Add a task and do some operations to generate activity entries
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Test Task", "--priority", "high"],
                  obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    runner.invoke(cli, ["task", "set-status", task_id, "ready", "--actor", "alice"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "start", task_id, "--actor", "alice"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "done", task_id, "--actor", "alice", "--note", "All done!"], obj={"cwd": tmp_path})

    # Add an issue
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Test Issue", "--description", "Test", "--severity", "high"],
                  obj={"cwd": tmp_path})

    # Edit the epic to generate more activity
    runner.invoke(cli, ["epic", "edit", "projects/demo/test", "--title", "Updated Epic", "--actor", "alice"],
                  obj={"cwd": tmp_path})

    return tmp_path


def test_activity_command_shows_entries(tmp_path: Path):
    repo = _repo_with_activity(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["activity", "--limit", "20"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Status changed" in result.output or "Created" in result.output


def test_activity_command_json(tmp_path: Path):
    repo = _repo_with_activity(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["activity", "--json", "--limit", "5"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    entries = json.loads(result.output)
    assert isinstance(entries, list)
    assert len(entries) > 0
    for e in entries:
        assert "date" in e
        assert "action" in e
        assert "actor" in e
        assert "entity_type" in e


def test_activity_command_filter_by_type(tmp_path: Path):
    repo = _repo_with_activity(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["activity", "--type", "task", "--limit", "10"], obj={"cwd": repo})
    assert result.exit_code == 0
    # Should only show task-related activity
    assert "task" in result.output.lower() or "✅" in result.output


def test_activity_command_filter_by_actor(tmp_path: Path):
    repo = _repo_with_activity(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["activity", "--actor", "alice", "--limit", "10"], obj={"cwd": repo})
    assert result.exit_code == 0
    # All entries should be by alice
    for line in result.output.split("\n"):
        if "by " in line:
            assert "alice" in line


def test_activity_command_no_activity(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."],
                  obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["activity"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "No activity" in result.output


def test_activity_command_since(tmp_path: Path):
    repo = _repo_with_activity(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["activity", "--since", "2099-01-01", "--limit", "10"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "No activity" in result.output
