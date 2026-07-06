import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_issues(tmp_path: Path) -> Path:
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

    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "High Open Issue", "--description", "Test", "--severity", "high"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--title", "Low Open Issue", "--description", "Test", "--severity", "low"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "bob@example.com",
                        "--title", "Medium Done Issue", "--description", "Test", "--severity", "medium"], obj={"cwd": tmp_path})

    # Assign and close the third issue
    issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    issue3_id = issue_files[2].stem.split("-")[0] + "-" + issue_files[2].stem.split("-")[1] + "-" + issue_files[2].stem.split("-")[2]
    runner.invoke(cli, ["issue", "assign", issue3_id, "bob", "--actor", "alice"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "close", issue3_id, "--closer", "alice", "--status", "done", "--note", "Fixed"], obj={"cwd": tmp_path})

    # Assign first issue to alice
    issue1_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    runner.invoke(cli, ["issue", "assign", issue1_id, "alice", "--actor", "alice"], obj={"cwd": tmp_path})

    return tmp_path


def test_issue_list_filter_by_status(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--status", "open", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    issues = json.loads(result.output)
    assert len(issues) == 2
    for i in issues:
        assert i["status"] == "open"


def test_issue_list_filter_by_severity(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--severity", "high", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    issues = json.loads(result.output)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_issue_list_filter_by_owner(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--owner", "bob", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    issues = json.loads(result.output)
    assert len(issues) == 1
    assert issues[0]["owner"] == "bob"


def test_issue_list_filter_combined(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--status", "open", "--severity", "high", "--json"],
                                obj={"cwd": repo})
    assert result.exit_code == 0
    issues = json.loads(result.output)
    assert len(issues) == 1
    assert issues[0]["status"] == "open"
    assert issues[0]["severity"] == "high"


def test_issue_list_filter_no_match(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--status", "wontfix", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    issues = json.loads(result.output)
    assert len(issues) == 0


def test_issue_list_text_shows_owner(tmp_path: Path):
    repo = _repo_with_issues(tmp_path)
    result = CliRunner().invoke(cli, ["issue", "list", "--owner", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "@alice" in result.output
    assert "High Open Issue" in result.output
