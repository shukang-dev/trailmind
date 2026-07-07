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
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo App", "--goal", "Build a demo."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test Epic",
                        "--goal", "Testing things", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Build the widget", "--priority", "high"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Fix the gizmo", "--priority", "low"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Widget crashes on startup", "--description", "The widget crashes when starting",
                        "--severity", "high"],
                  obj={"cwd": tmp_path})
    return tmp_path


def test_search_finds_tasks_by_title(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "widget"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Build the widget" in result.output
    assert "Widget crashes" in result.output


def test_search_filters_by_type(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "widget", "--type", "task"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Build the widget" in result.output
    assert "Widget crashes" not in result.output  # issue excluded


def test_search_filters_by_multiple_types(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "gizmo", "--type", "task,issue"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Fix the gizmo" in result.output


def test_search_no_results(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "nonexistent_xyz"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "No results found" in result.output


def test_search_json_output(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "widget", "--json", "--limit", "5"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 2
    for r in data:
        assert "entity_type" in r
        assert "title" in r
        assert "path" in r


def test_search_limit(tmp_path: Path):
    repo = _repo_with_data(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "widget", "--json", "--limit", "1"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert len(data) == 1
