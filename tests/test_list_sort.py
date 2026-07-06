from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_tasks_and_issues(tmp_path: Path) -> Path:
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

    # Add tasks with various priorities/due dates
    tasks = [
        ("Low task", "alice", "low", "2026-12-31"),
        ("High task", "alice", "high", "2026-07-15"),
        ("Critical task", "bob", "critical", "2026-07-10"),
        ("Medium task", "bob", "medium", "2026-08-01"),
    ]
    task_ids = []
    for title, owner, priority, due in tasks:
        runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                            f"--owner", f"{owner}@example.com", "--title", title, "--priority", priority],
                       obj={"cwd": tmp_path})
        task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
        task_id = task_files[-1].stem.split("-")[0] + "-" + task_files[-1].stem.split("-")[1] + "-" + task_files[-1].stem.split("-")[2]
        task_ids.append(task_id)
        # Set due date
        runner.invoke(cli, ["task", "due", task_id, due, "--actor", "alice"], obj={"cwd": tmp_path})

    # Add issues with various severities
    issues = [
        ("Low issue", "alice", "low"),
        ("Critical issue", "bob", "critical"),
        ("High issue", "alice", "high"),
    ]
    for title, filer, severity in issues:
        runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", f"{filer}@example.com",
                            "--title", title, "--description", "Test", "--severity", severity], obj={"cwd": tmp_path})

    return tmp_path


def test_task_list_sort_by_priority(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--sort", "priority"], obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    # Critical should come before High which comes before Medium which comes before Low
    assert lines.index("Critical task") < lines.index("High task")
    assert lines.index("High task") < lines.index("Medium task")
    assert lines.index("Medium task") < lines.index("Low task")


def test_task_list_sort_by_due(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--sort", "due"], obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    # Earliest due first: 2026-07-10 (Critical) < 2026-07-15 (High) < 2026-08-01 (Medium) < 2026-12-31 (Low)
    assert lines.index("Critical task") < lines.index("High task")
    assert lines.index("High task") < lines.index("Medium task")
    assert lines.index("Medium task") < lines.index("Low task")


def test_task_list_sort_by_title(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--sort", "title"], obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    # Alphabetical: Critical < High < Low < Medium
    assert lines.index("Critical task") < lines.index("High task")
    assert lines.index("High task") < lines.index("Low task")
    assert lines.index("Low task") < lines.index("Medium task")


def test_issue_list_sort_by_severity(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--epic", "projects/demo/test", "--sort", "severity"], obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    # Critical < High < Low
    assert lines.index("Critical issue") < lines.index("High issue")
    assert lines.index("High issue") < lines.index("Low issue")


def test_issue_list_sort_by_title(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--epic", "projects/demo/test", "--sort", "title"], obj={"cwd": repo})
    assert result.exit_code == 0
    lines = result.output
    # Alphabetical: Critical < High < Low
    assert lines.index("Critical issue") < lines.index("High issue")
    assert lines.index("High issue") < lines.index("Low issue")


def test_task_list_sort_default_is_created(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    # Without --sort, should work fine
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Critical task" in result.output


def test_task_list_sort_with_filter(tmp_path: Path):
    repo = _repo_with_tasks_and_issues(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--owner", "alice", "--sort", "priority"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    # Only alice's tasks: High and Low
    assert "High task" in result.output
    assert "Low task" in result.output
    assert "Critical task" not in result.output  # bob's task
