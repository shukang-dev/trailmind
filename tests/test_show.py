import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.show import format_entity_show, show_entity


def _repo_with_data(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    """Create a repo with one task, issue, milestone, and inbox item."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})

    task_result = runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task", "--code-paths", "src/app.py", "--deliverables", "tests pass"], obj={"cwd": tmp_path})
    assert task_result.exit_code == 0

    issue_result = runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--title", "Test Issue", "--description", "Testing", "--severity", "high"], obj={"cwd": tmp_path})
    assert issue_result.exit_code == 0

    ms_result = runner.invoke(cli, ["milestone", "add", "--epic", "projects/demo/test", "--title", "Test Milestone", "--date", "2026-07-15"], obj={"cwd": tmp_path})
    assert ms_result.exit_code == 0

    inbox_result = runner.invoke(cli, ["inbox", "add", "--epic", "projects/demo/test", "--author", "alice", "--title", "Test Inbox", "--note", "Testing"], obj={"cwd": tmp_path})
    assert inbox_result.exit_code == 0

    # Extract IDs
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]

    issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]

    ms_files = sorted((tmp_path / "projects" / "demo" / "test" / "milestones").glob("M-*.md"))
    ms_id = ms_files[0].stem

    inbox_files = sorted((tmp_path / "projects" / "demo" / "test" / "inbox").glob("IN-*.md"))
    inbox_id = inbox_files[0].stem

    return tmp_path, task_id, issue_id, ms_id, inbox_id


def test_task_show_text(tmp_path: Path):
    repo, task_id, _issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["task", "show", task_id], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Test Task" in result.output
    assert "owner" in result.output
    assert "code_paths" in result.output


def test_task_show_json(tmp_path: Path):
    repo, task_id, _issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["task", "show", task_id, "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "Test Task"
    assert data["status"] == "created"
    assert "src/app.py" in data.get("code_paths", [])


def test_issue_show_text(tmp_path: Path):
    repo, _task_id, issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "show", issue_id], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Test Issue" in result.output
    assert "severity" in result.output


def test_issue_show_json(tmp_path: Path):
    repo, _task_id, issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "show", issue_id, "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "Test Issue"
    assert data["severity"] == "high"


def test_milestone_show_text(tmp_path: Path):
    repo, _task_id, _issue_id, ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["milestone", "show", ms_id], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Test Milestone" in result.output
    assert "date" in result.output


def test_milestone_show_json(tmp_path: Path):
    repo, _task_id, _issue_id, ms_id, _inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["milestone", "show", ms_id, "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "Test Milestone"
    assert data["date"] == "2026-07-15"


def test_inbox_show_text(tmp_path: Path):
    repo, _task_id, _issue_id, _ms_id, inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["inbox", "show", inbox_id], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Test Inbox" in result.output


def test_inbox_show_json(tmp_path: Path):
    repo, _task_id, _issue_id, _ms_id, inbox_id = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["inbox", "show", inbox_id, "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "Test Inbox"
    assert data["status"] == "open"


def test_show_entity_includes_path(tmp_path: Path):
    repo, task_id, _issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    data = show_entity(repo, task_id, "T")
    assert "path" in data
    assert "tasks" in data["path"]


def test_format_entity_show_includes_body(tmp_path: Path):
    repo, task_id, _issue_id, _ms_id, _inbox_id = _repo_with_data(tmp_path)
    data = show_entity(repo, task_id, "T")
    rendered = format_entity_show(data, entity_label="Task")
    assert "Body" in rendered
    assert "Test Task" in rendered


def test_task_show_missing_is_error(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("developers: []\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["task", "show", "T-999999-999"], obj={"cwd": tmp_path})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
