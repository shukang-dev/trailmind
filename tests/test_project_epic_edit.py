from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: bob@example.com\n  shortname: bob\n  uid: '654321'\n  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Build a demo.",
                        "--owners", "alice@example.com", "--tags", "test"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test Epic",
                        "--goal", "Testing things.", "--start", "2026-07-01", "--target", "2026-07-31",
                        "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    return tmp_path


def test_project_edit_title(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "edit", "demo", "--title", "New Demo", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["title"] == "New Demo"
    assert "New Demo" in body
    assert "Edited project" in body


def test_project_edit_goal(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "edit", "demo", "--goal", "New goal here.", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["goal"] == "New goal here."
    assert "New goal here." in body


def test_project_edit_owners_and_tags(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "edit", "demo", "--owners", "alice@example.com,bob@example.com",
                                 "--tags", "demo,production", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, _body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["owners"] == ["alice@example.com", "bob@example.com"]
    assert fm["tags"] == ["demo", "production"]


def test_project_edit_no_fields_is_error(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "edit", "demo", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_epic_edit_title(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "edit", "projects/demo/test", "--title", "Updated Epic", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "test" / "EPIC.md")
    assert fm["title"] == "Updated Epic"
    assert "Updated Epic" in body
    assert "Edited epic" in body


def test_epic_edit_goal_and_target(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "edit", "projects/demo/test", "--goal", "Updated goal.", "--target", "2026-08-15",
                                 "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "test" / "EPIC.md")
    assert fm["goal"] == "Updated goal."
    assert fm["target"] == "2026-08-15"
    assert "Updated goal." in body


def test_epic_edit_roster_and_repos(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "edit", "projects/demo/test", "--roster", "alice,bob", "--repos", "demo,backend",
                                 "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, _body = read_entity(repo / "projects" / "demo" / "test" / "EPIC.md")
    assert fm["roster"] == ["alice", "bob"]
    assert fm["repos"] == ["demo", "backend"]


def test_epic_edit_no_fields_is_error(tmp_path: Path):
    repo = _repo_with_project(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "edit", "projects/demo/test", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
