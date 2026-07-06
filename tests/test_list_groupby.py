from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_data(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: bob@example.com\n  shortname: bob\n  uid: '654321'\n  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing",
                        "--roster", "alice,bob", "--repos", "demo"], obj={"cwd": tmp_path})

    # Add tasks
    for title, owner, priority in [
        ("Critical task", "alice", "critical"),
        ("High task", "bob", "high"),
        ("Medium task", "alice", "medium"),
        ("Low task", "bob", "low"),
    ]:
        runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                            f"--owner", f"{owner}@example.com", "--title", title, "--priority", priority],
                       obj={"cwd": tmp_path})

    # Add issues
    for title, filer, severity in [
        ("Critical issue", "alice", "critical"),
        ("High issue", "bob", "high"),
        ("Low issue", "alice", "low"),
    ]:
        runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", f"{filer}@example.com",
                            "--title", title, "--description", "Test", "--severity", severity], obj={"cwd": tmp_path})
        # Assign issues
        issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
        issue_id = issue_files[-1].stem.split("-")[0] + "-" + issue_files[-1].stem.split("-")[1] + "-" + issue_files[-1].stem.split("-")[2]
        runner.invoke(cli, ["issue", "assign", issue_id, filer, "--actor", "alice"], obj={"cwd": tmp_path})

    return tmp_path


def test_task_list_group_by_status(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--group-by", "status"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    assert "CREATED" in result.output
    assert "Critical task" in result.output


def test_task_list_group_by_owner(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--group-by", "owner"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    assert "ALICE" in result.output
    assert "BOB" in result.output


def test_task_list_group_by_priority(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--group-by", "priority"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    # Critical should come before High
    lines = result.output
    assert lines.index("CRITICAL") < lines.index("HIGH")
    assert lines.index("HIGH") < lines.index("MEDIUM")
    assert lines.index("MEDIUM") < lines.index("LOW")


def test_task_list_group_by_no_tasks(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing",
                        "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["task", "list", "--group-by", "status"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "No tasks" in result.output


def test_issue_list_group_by_severity(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--epic", "projects/demo/test", "--group-by", "severity"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    assert lines.index("CRITICAL") < lines.index("HIGH")
    assert lines.index("HIGH") < lines.index("LOW")


def test_issue_list_group_by_owner(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--epic", "projects/demo/test", "--group-by", "owner"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    # Should show grouped output with owner headers
    assert "(" in result.output  # group count header
