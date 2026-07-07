from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_two_epics(tmp_path: Path) -> tuple[Path, str, str, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "epic_a", "--title", "Epic A",
                        "--goal", "First.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "epic_b", "--title", "Epic B",
                        "--goal", "Second.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/epic_a", "--filer", "alice@example.com",
                        "--title", "Movable Issue", "--description", "Test", "--severity", "high"],
                  obj={"cwd": tmp_path})

    issue_files = sorted((tmp_path / "projects" / "demo" / "epic_a" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    return tmp_path, issue_id, "projects/demo/epic_a", "projects/demo/epic_b"


def test_issue_move(tmp_path: Path):
    repo, issue_id, epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "move", issue_id, epic_b, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    issue_files_b = list((repo / "projects" / "demo" / "epic_b" / "issues").glob("I-*movable-issue.md"))
    assert len(issue_files_b) == 1
    issue_files_a = list((repo / "projects" / "demo" / "epic_a" / "issues").glob("I-*movable-issue.md"))
    assert len(issue_files_a) == 0

    fm, body = read_entity(issue_files_b[0])
    assert "Moved" in body


def test_issue_move_same_epic_is_error(tmp_path: Path):
    repo, issue_id, epic_a, _epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "move", issue_id, epic_a, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code != 0
    assert "already" in result.output


def test_issue_move_preserves_metadata(tmp_path: Path):
    repo, issue_id, _epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "move", issue_id, epic_b, "--actor", "alice", "--note", "Reorg"],
                            obj={"cwd": repo})
    assert result.exit_code == 0
    issue_files_b = list((repo / "projects" / "demo" / "epic_b" / "issues").glob("I-*movable-issue.md"))
    fm, body = read_entity(issue_files_b[0])
    assert fm["title"] == "Movable Issue"
    assert fm["severity"] == "high"
    assert "Reorg" in body


def test_issue_move_list_from_target(tmp_path: Path):
    repo, issue_id, _epic_a, epic_b = _repo_with_two_epics(repo := tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["issue", "move", issue_id, epic_b, "--actor", "alice"], obj={"cwd": repo})
    result = runner.invoke(cli, ["issue", "list", "--epic", epic_b], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "Movable Issue" in result.output
