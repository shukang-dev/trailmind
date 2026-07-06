from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_done_task(tmp_path: Path) -> tuple[Path, str]:
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
                        "--owner", "alice@example.com", "--title", "Done Task"], obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    runner.invoke(cli, ["task", "done", task_id, "--actor", "alice"], obj={"cwd": tmp_path})
    return tmp_path, task_id


def _repo_with_closed_issue(tmp_path: Path) -> tuple[Path, str]:
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
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Closed Issue", "--description", "Test", "--severity", "high"], obj={"cwd": tmp_path})
    issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    runner.invoke(cli, ["issue", "close", issue_id, "--closer", "alice", "--status", "done", "--note", "Fixed"],
                  obj={"cwd": tmp_path})
    return tmp_path, issue_id


def test_task_reopen_defaults_to_ready(tmp_path: Path):
    repo, task_id = _repo_with_done_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "reopen", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["status"] == "ready"
    assert "Reopened" in body


def test_task_reopen_to_in_progress(tmp_path: Path):
    repo, task_id = _repo_with_done_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "reopen", task_id, "--to", "in_progress", "--actor", "alice", "--note", "Need more work"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["status"] == "in_progress"
    assert "Need more work" in body


def test_task_reopen_with_note(tmp_path: Path):
    repo, task_id = _repo_with_done_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "reopen", task_id, "--actor", "alice", "--note", "Found new requirements"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    _fm, body = read_entity(task_file)
    assert "Found new requirements" in body


def test_task_reopen_open_task_is_error(tmp_path: Path):
    repo, _ = _repo_with_done_task(repo := tmp_path)
    # Add a task that's not done
    runner = CliRunner()
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Open Task"], obj={"cwd": repo})
    task_files = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    open_task = task_files[-1]
    open_id = open_task.stem.split("-")[0] + "-" + open_task.stem.split("-")[1] + "-" + open_task.stem.split("-")[2]

    result = runner.invoke(cli, ["task", "reopen", open_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "cannot reopen" in result.output


def test_issue_reopen(tmp_path: Path):
    repo, issue_id = _repo_with_closed_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "reopen", issue_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, body = read_entity(issue_file)
    assert fm["status"] == "open"
    assert "Reopened" in body


def test_issue_reopen_with_note(tmp_path: Path):
    repo, issue_id = _repo_with_closed_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "reopen", issue_id, "--actor", "alice", "--note", "Still happening"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    _fm, body = read_entity(issue_file)
    assert "Still happening" in body


def test_issue_reopen_open_issue_is_error(tmp_path: Path):
    repo, _ = _repo_with_closed_issue(repo := tmp_path)
    # Add an issue that's still open
    runner = CliRunner()
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Open Issue", "--description", "Test", "--severity", "low"], obj={"cwd": repo})
    issue_files = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    open_issue = issue_files[-1]
    open_id = open_issue.stem.split("-")[0] + "-" + open_issue.stem.split("-")[1] + "-" + open_issue.stem.split("-")[2]

    result = runner.invoke(cli, ["issue", "reopen", open_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
