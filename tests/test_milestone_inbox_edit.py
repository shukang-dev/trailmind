from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_milestone_and_inbox(tmp_path: Path) -> Path:
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
    runner.invoke(cli, ["milestone", "add", "--epic", "projects/demo/test", "--title", "Alpha Release",
                        "--date", "2026-08-01"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["inbox", "add", "--epic", "projects/demo/test", "--title", "Review design doc",
                        "--author", "alice@example.com", "--note", "Need to review"], obj={"cwd": tmp_path})
    return tmp_path


def test_milestone_edit_title(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    ms_files = sorted((repo / "projects" / "demo" / "test" / "milestones").glob("M-*.md"))
    ms_id = ms_files[0].stem.split("-")[0] + "-" + ms_files[0].stem.split("-")[1] + "-" + ms_files[0].stem.split("-")[2]

    result = runner.invoke(cli, ["milestone", "edit", ms_id, "--title", "Beta Release", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(ms_files[0])
    assert fm["title"] == "Beta Release"
    assert "Edited milestone" in body


def test_milestone_edit_date(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    ms_files = sorted((repo / "projects" / "demo" / "test" / "milestones").glob("M-*.md"))
    ms_id = ms_files[0].stem.split("-")[0] + "-" + ms_files[0].stem.split("-")[1] + "-" + ms_files[0].stem.split("-")[2]

    result = runner.invoke(cli, ["milestone", "edit", ms_id, "--date", "2026-09-15", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    fm, _body = read_entity(ms_files[0])
    assert fm["date"] == "2026-09-15"


def test_milestone_edit_status(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    ms_files = sorted((repo / "projects" / "demo" / "test" / "milestones").glob("M-*.md"))
    ms_id = ms_files[0].stem.split("-")[0] + "-" + ms_files[0].stem.split("-")[1] + "-" + ms_files[0].stem.split("-")[2]

    result = runner.invoke(cli, ["milestone", "edit", ms_id, "--status", "done", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    fm, _body = read_entity(ms_files[0])
    assert fm["status"] == "done"


def test_milestone_edit_no_fields_is_error(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    ms_files = sorted((repo / "projects" / "demo" / "test" / "milestones").glob("M-*.md"))
    ms_id = ms_files[0].stem.split("-")[0] + "-" + ms_files[0].stem.split("-")[1] + "-" + ms_files[0].stem.split("-")[2]

    result = runner.invoke(cli, ["milestone", "edit", ms_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_inbox_edit_title(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    inbox_files = sorted((repo / "projects" / "demo" / "test" / "inbox").glob("IN-*.md"))
    in_id = inbox_files[0].stem  # IN-YYYYMMDD-NNN-title

    result = runner.invoke(cli, ["inbox", "edit", in_id, "--title", "Updated review task", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(inbox_files[0])
    assert fm["title"] == "Updated review task"
    assert "Edited inbox" in body


def test_inbox_edit_no_fields_is_error(tmp_path: Path):
    repo = _repo_with_milestone_and_inbox(repo := tmp_path)
    runner = CliRunner()
    inbox_files = sorted((repo / "projects" / "demo" / "test" / "inbox").glob("IN-*.md"))
    in_id = inbox_files[0].stem

    result = runner.invoke(cli, ["inbox", "edit", in_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code != 0
    assert "error:" in result.output
    assert "Traceback" not in result.output
