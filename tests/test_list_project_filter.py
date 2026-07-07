from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_two_projects(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    # Project A
    runner.invoke(cli, ["project", "init", "--slug", "alpha", "--title", "Alpha", "--goal", "Project A."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "alpha", "--slug", "core", "--title", "Core",
                        "--goal", "Core features.", "--roster", "alice", "--repos", "alpha"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/alpha/core", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Alpha Task 1", "--priority", "high"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/alpha/core", "--filer", "alice@example.com",
                        "--title", "Alpha Bug 1", "--description", "Test", "--severity", "high"],
                  obj={"cwd": tmp_path})

    # Project B
    runner.invoke(cli, ["project", "init", "--slug", "beta", "--title", "Beta", "--goal", "Project B."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "beta", "--slug", "web", "--title", "Web",
                        "--goal", "Web UI.", "--roster", "alice", "--repos", "beta"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/beta/web", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Beta Task 1", "--priority", "low"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/beta/web", "--filer", "alice@example.com",
                        "--title", "Beta Bug 1", "--description", "Test", "--severity", "low"],
                  obj={"cwd": tmp_path})

    return tmp_path


def test_task_list_filter_by_project(tmp_path: Path):
    repo = _repo_with_two_projects(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--project", "alpha"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Alpha Task 1" in result.output
    assert "Beta Task 1" not in result.output


def test_task_list_filter_by_project_beta(tmp_path: Path):
    repo = _repo_with_two_projects(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--project", "beta"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Beta Task 1" in result.output
    assert "Alpha Task 1" not in result.output


def test_issue_list_filter_by_project(tmp_path: Path):
    repo = _repo_with_two_projects(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--project", "alpha"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Alpha Bug 1" in result.output
    assert "Beta Bug 1" not in result.output


def test_task_list_project_not_found(tmp_path: Path):
    repo = _repo_with_two_projects(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--project", "nonexistent"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "not found" in result.output


def test_task_list_project_and_epic_are_mutually_exclusive(tmp_path: Path):
    repo = _repo_with_two_projects(repo := tmp_path)
    runner = CliRunner()
    # When both are provided, epic takes precedence (it's more specific)
    result = runner.invoke(cli, ["task", "list", "--project", "alpha", "--epic", "projects/beta/web"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Beta Task 1" in result.output
    assert "Alpha Task 1" not in result.output
