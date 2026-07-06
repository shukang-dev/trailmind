from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_tasks(tmp_path: Path) -> Path:
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

    # Add tasks with various priorities and due dates
    tasks = [
        ("Low priority ready", "alice", "ready", "low", "2026-12-31"),
        ("High priority ready", "alice", "ready", "high", "2026-07-15"),
        ("Critical ready", "alice", "ready", "critical", "2026-07-10"),
        ("Medium created", "bob", "created", "medium", "2026-08-01"),
        ("Done task", "alice", "done", "high", "2026-06-01"),
        ("Blocked task", "alice", "blocked", "high", "2026-07-20"),
        ("In progress", "bob", "in_progress", "medium", "2026-07-18"),
        ("No due date", "alice", "ready", "medium", ""),
    ]
    for title, owner, status, priority, due in tasks:
        runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                            f"--owner", f"{owner}@example.com", "--title", title, "--priority", priority],
                       obj={"cwd": tmp_path})
        task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
        task_id = task_files[-1].stem.split("-")[0] + "-" + task_files[-1].stem.split("-")[1] + "-" + task_files[-1].stem.split("-")[2]
        if status != "created":
            if status == "done":
                runner.invoke(cli, ["task", "done", task_id, "--actor", "alice"], obj={"cwd": tmp_path})
            elif status == "in_progress":
                runner.invoke(cli, ["task", "start", task_id, "--actor", "alice"], obj={"cwd": tmp_path})
            elif status == "blocked":
                runner.invoke(cli, ["task", "set-status", task_id, "blocked", "--actor", "alice"], obj={"cwd": tmp_path})
            elif status == "ready":
                runner.invoke(cli, ["task", "set-status", task_id, "ready", "--actor", "alice"], obj={"cwd": tmp_path})
        if due:
            runner.invoke(cli, ["task", "due", task_id, due, "--actor", "alice"], obj={"cwd": tmp_path})

    return tmp_path


def test_task_next_shows_most_actionable_first(tmp_path: Path):
    repo = _repo_with_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "next"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Next tasks" in result.output

    # In-progress should be first, then critical, then high, then medium
    lines = result.output
    # Critical should appear before high
    assert lines.index("Critical ready") < lines.index("High priority ready")
    # High before medium
    assert lines.index("High priority ready") < lines.index("Medium created")
    # Done tasks should NOT appear
    assert "Done task" not in lines
    # Blocked should NOT appear
    assert "Blocked task" not in lines


def test_task_next_filter_by_owner(tmp_path: Path):
    repo = _repo_with_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "next", "--owner", "bob"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Medium created" in result.output
    assert "Critical ready" not in result.output


def test_task_next_limit(tmp_path: Path):
    repo = _repo_with_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "next", "--limit", "2"], obj={"cwd": repo})
    assert result.exit_code == 0
    # Should only show 2 tasks (count numbered items)
    numbered = [l for l in result.output.split("\n") if l.strip().startswith(("1.", "2.", "3.", "4.", "5."))]
    assert len(numbered) == 2


def test_task_next_json(tmp_path: Path):
    repo = _repo_with_tasks(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "next", "--json", "--limit", "3"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert isinstance(tasks, list)
    assert len(tasks) == 3
    # No internal keys
    for t in tasks:
        assert "_in_progress" not in t
    # First should be in_progress or critical
    assert tasks[0]["status"] in ("in_progress", "ready")


def test_task_next_no_tasks(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing",
                        "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})

    result = runner.invoke(cli, ["task", "next"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "No actionable tasks" in result.output or "All caught up" in result.output
