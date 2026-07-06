from datetime import date, timedelta
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_filtered_tasks(tmp_path: Path) -> Path:
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

    # Task 1: alice, high priority, in_progress
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "High Priority Task",
                        "--priority", "high"], obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task1_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    runner.invoke(cli, ["task", "start", task1_id, "--actor", "alice"], obj={"cwd": tmp_path})

    # Task 2: bob, low priority
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "bob@example.com", "--title", "Low Priority Task",
                        "--priority", "low"], obj={"cwd": tmp_path})

    # Task 3: alice, medium, with due date soon
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Due Soon Task",
                        "--priority", "medium"], obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task3 = task_files[-1]
    task3_id = task3.stem.split("-")[0] + "-" + task3.stem.split("-")[1] + "-" + task3.stem.split("-")[2]
    runner.invoke(cli, ["task", "due", task3_id, tomorrow, "--actor", "alice"], obj={"cwd": tmp_path})

    # Task 4: alice, overdue (due yesterday)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Overdue Task",
                        "--priority", "high"], obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task4 = task_files[-1]
    task4_id = task4.stem.split("-")[0] + "-" + task4.stem.split("-")[1] + "-" + task4.stem.split("-")[2]
    runner.invoke(cli, ["task", "due", task4_id, yesterday, "--actor", "alice"], obj={"cwd": tmp_path})

    return tmp_path


def test_task_list_filter_by_status(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--status", "in_progress", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "High Priority Task"


def test_task_list_filter_by_owner(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--owner", "bob", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 1
    assert tasks[0]["owner"] == "bob"


def test_task_list_filter_by_priority(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--priority", "high", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 2
    for t in tasks:
        assert t["priority"] == "high"


def test_task_list_filter_overdue(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--overdue", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Overdue Task"


def test_task_list_filter_due_before(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--due-before", (date.today() + timedelta(days=2)).isoformat(), "--json"],
                                obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    # Should include due tomorrow and due yesterday
    assert len(tasks) == 2


def test_task_list_filter_combined(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--owner", "alice", "--priority", "high", "--status", "in_progress", "--json"],
                                obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "High Priority Task"


def test_task_list_filter_no_match(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--status", "done", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    tasks = json.loads(result.output)
    assert len(tasks) == 0


def test_task_list_text_shows_priority_and_due(tmp_path: Path):
    repo = _repo_with_filtered_tasks(tmp_path)
    result = CliRunner().invoke(cli, ["task", "list", "--owner", "bob"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Low Priority Task" in result.output
    assert "[low]" in result.output
