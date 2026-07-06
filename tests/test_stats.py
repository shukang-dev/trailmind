import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.stats import build_stats, format_stats


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

    # Tasks
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task 1", "--priority", "high"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "bob@example.com", "--title", "Task 2", "--priority", "low"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task 3", "--priority", "medium"], obj={"cwd": tmp_path})

    # Start task 1
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task1_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    runner.invoke(cli, ["task", "start", task1_id, "--actor", "alice"], obj={"cwd": tmp_path})

    # Issue
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Issue 1", "--description", "Test", "--severity", "high"], obj={"cwd": tmp_path})

    # Milestone
    runner.invoke(cli, ["milestone", "add", "--epic", "projects/demo/test", "--title", "M1", "--date", "2026-07-15"], obj={"cwd": tmp_path})

    # Inbox
    runner.invoke(cli, ["inbox", "add", "--epic", "projects/demo/test", "--author", "alice",
                        "--title", "Inbox 1", "--note", "Test"], obj={"cwd": tmp_path})

    return tmp_path


def test_build_stats_counts(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    assert stats["projects"] == 1
    assert stats["epics"] == 1
    assert stats["milestones"] == 1
    assert stats["tasks"]["total"] == 3
    assert stats["issues"]["total"] == 1
    assert stats["inbox"]["total"] == 1
    assert stats["inbox"]["open"] == 1


def test_build_stats_by_status(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    assert stats["tasks"]["by_status"]["in_progress"] == 1
    assert stats["tasks"]["by_status"]["created"] == 2


def test_build_stats_by_priority(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    assert stats["tasks"]["by_priority"]["high"] == 1
    assert stats["tasks"]["by_priority"]["medium"] == 1
    assert stats["tasks"]["by_priority"]["low"] == 1


def test_build_stats_by_owner(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    assert stats["tasks"]["by_owner"]["alice"] == 2
    assert stats["tasks"]["by_owner"]["bob"] == 1


def test_build_stats_issues(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    assert stats["issues"]["by_severity"]["high"] == 1


def test_build_stats_empty_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    stats = build_stats(tmp_path)
    assert stats["projects"] == 0
    assert stats["tasks"]["total"] == 0


def test_format_stats_readable(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    stats = build_stats(repo)
    rendered = format_stats(stats)
    assert "Projects:" in rendered
    assert "Tasks:" in rendered
    assert "By status:" in rendered
    assert "By priority:" in rendered
    assert "Issues:" in rendered
    assert "Inbox:" in rendered


def test_stats_cli_text(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["stats"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Projects:" in result.output
    assert "Tasks:      3" in result.output


def test_stats_cli_json(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["stats", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["projects"] == 1
    assert data["tasks"]["total"] == 3
    assert data["issues"]["total"] == 1
