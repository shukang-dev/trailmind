from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_project_and_epic(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo App", "--goal", "Build a demo."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "mvp", "--title", "MVP",
                        "--goal", "First release.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    return tmp_path


def test_project_show(tmp_path: Path):
    repo = _repo_with_project_and_epic(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "demo"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Project: Demo App" in result.output
    assert "demo" in result.output
    assert "Build a demo" in result.output


def test_project_show_json(tmp_path: Path):
    repo = _repo_with_project_and_epic(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "demo", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["slug"] == "demo"
    assert data["title"] == "Demo App"
    assert "path" in data


def test_project_show_not_found(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "nonexistent"], obj={"cwd": tmp_path})
    assert result.exit_code != 0
    assert "not found" in result.output


def test_epic_show(tmp_path: Path):
    repo = _repo_with_project_and_epic(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "show", "projects/demo/mvp"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Epic: MVP" in result.output
    assert "mvp" in result.output
    assert "First release" in result.output


def test_epic_show_json(tmp_path: Path):
    repo = _repo_with_project_and_epic(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "show", "projects/demo/mvp", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["slug"] == "mvp"
    assert data["title"] == "MVP"
    assert "path" in data


def test_epic_show_not_found(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "show", "projects/nonexistent/foo"], obj={"cwd": tmp_path})
    assert result.exit_code != 0
