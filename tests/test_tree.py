from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_data(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo App", "--goal", "Build."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "mvp", "--title", "MVP",
                        "--goal", "First release.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "auth", "--title", "Auth",
                        "--goal", "Auth system.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task 1", "--priority", "high"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Task 2", "--priority", "low"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--title", "Bug 1", "--description", "Test", "--severity", "high"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["milestone", "add", "--epic", "projects/demo/mvp", "--title", "Alpha",
                        "--date", "2026-08-01"], obj={"cwd": tmp_path})
    return tmp_path


def test_tree_command_shows_structure(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["tree"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "projects/" in result.output
    assert "demo" in result.output
    assert "mvp" in result.output
    assert "auth" in result.output
    assert "Task 1" not in result.output  # tree shows counts, not individual tasks


def test_tree_command_shows_counts(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["tree"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "2 tasks" in result.output or "✅ 2" in result.output
    assert "1 issues" in result.output or "🐛 1" in result.output
    assert "1 milestones" in result.output or "🏁 1" in result.output


def test_tree_command_json(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["tree", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "projects" in data
    assert data["project_count"] == 1
    assert len(data["projects"]) == 1
    proj = data["projects"][0]
    assert proj["slug"] == "demo"
    assert proj["epic_count"] == 2


def test_tree_empty_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["tree"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "0 projects" in result.output or "projects/" in result.output
