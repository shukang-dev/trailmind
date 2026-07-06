from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_issue(tmp_path: Path) -> tuple[Path, str]:
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
                        "--title", "Original Title", "--description", "Original description.",
                        "--severity", "high"], obj={"cwd": tmp_path})
    issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    return tmp_path, issue_id


def test_issue_edit_title(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "edit", issue_id, "--title", "New Title", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, body = read_entity(issue_file)
    assert fm["title"] == "New Title"
    assert "Edited issue" in body
    assert "Original Title" in body
    assert "New Title" in body


def test_issue_edit_description(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "edit", issue_id, "--description", "Updated description.", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    _fm, body = read_entity(issue_file)
    assert "Updated description." in body


def test_issue_edit_multiple_fields(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "edit", issue_id, "--title", "Updated", "--description", "New desc.",
                                 "--actor", "alice", "--note", "Fixed all the things"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, body = read_entity(issue_file)
    assert fm["title"] == "Updated"
    assert "New desc." in body
    assert "Fixed all the things" in body


def test_issue_edit_no_fields_is_error(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "edit", issue_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
