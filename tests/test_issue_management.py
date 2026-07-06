from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.issue import ISSUE_SEVERITIES, validate_issue_severity


def _repo_with_issue(tmp_path: Path) -> tuple[Path, str]:
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
    result = runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                                 "--title", "Test Issue", "--description", "Testing", "--severity", "medium"],
                            obj={"cwd": tmp_path})
    assert result.exit_code == 0
    issue_files = sorted((tmp_path / "projects" / "demo" / "test" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    return tmp_path, issue_id


def test_issue_assign_changes_owner(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "assign", issue_id, "bob@example.com", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, body = read_entity(issue_file)
    assert fm["owner"] == "bob"
    assert "Assigned to bob" in body
    assert "was alice" in body


def test_issue_assign_with_shortname(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "assign", issue_id, "bob", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, _body = read_entity(issue_file)
    assert fm["owner"] == "bob"


def test_issue_assign_with_note(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "assign", issue_id, "bob", "--actor", "alice", "--note", "Bob owns this area"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    _fm, body = read_entity(issue_file)
    assert "Bob owns this area" in body


def test_issue_set_severity(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "set-severity", issue_id, "critical", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    fm, body = read_entity(issue_file)
    assert fm["severity"] == "critical"
    assert "Severity changed from medium to critical" in body


def test_issue_set_severity_with_note(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "set-severity", issue_id, "high", "--actor", "alice", "--note", "Production impact"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    issue_file = sorted((repo / "projects" / "demo" / "test" / "issues").glob("I-*.md"))[0]
    _fm, body = read_entity(issue_file)
    assert "Production impact" in body


def test_validate_issue_severity_valid():
    for s in ISSUE_SEVERITIES:
        assert validate_issue_severity(s) == s


def test_validate_issue_severity_case_insensitive():
    assert validate_issue_severity("HIGH") == "high"
    assert validate_issue_severity("Low") == "low"


def test_validate_issue_severity_invalid():
    from trailmind.errors import TrailmindError
    try:
        validate_issue_severity("urgent")
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "invalid issue severity" in str(exc)


def test_issue_list_shows_owner(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "@alice" in result.output


def test_issue_assign_unknown_user_is_error(tmp_path: Path):
    repo, issue_id = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "assign", issue_id, "charlie@example.com", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
