from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.epic import DEFAULT_EPIC_STATE, EPIC_STATES, validate_epic_state
from trailmind.project import DEFAULT_PROJECT_STATE, PROJECT_STATES, validate_project_state


def _repo_with_project_and_epic(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "mvp", "--title", "MVP", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    return tmp_path


def test_project_default_state(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    fm, _body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["state"] == DEFAULT_PROJECT_STATE


def test_epic_default_state(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    fm, _body = read_entity(repo / "projects" / "demo" / "mvp" / "EPIC.md")
    assert fm["state"] == DEFAULT_EPIC_STATE


def test_validate_project_state_valid():
    for s in PROJECT_STATES:
        assert validate_project_state(s) == s


def test_validate_project_state_case_insensitive():
    assert validate_project_state("ACTIVE") == "active"
    assert validate_project_state("Paused") == "paused"


def test_validate_project_state_invalid():
    from trailmind.errors import TrailmindError
    try:
        validate_project_state("unknown")
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "invalid project state" in str(exc)


def test_validate_epic_state_valid():
    for s in EPIC_STATES:
        assert validate_epic_state(s) == s


def test_validate_epic_state_invalid():
    from trailmind.errors import TrailmindError
    try:
        validate_epic_state("unknown")
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "invalid epic state" in str(exc)


def test_project_set_status_cli(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "set-status", "demo", "paused", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["state"] == "paused"
    assert "State changed from active to paused" in body


def test_project_set_status_with_note(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "set-status", "demo", "completed", "--actor", "alice", "--note", "All done"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "PROJECT.md")
    assert fm["state"] == "completed"
    assert "All done" in body


def test_epic_set_status_cli(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["epic", "set-status", "projects/demo/mvp", "completed", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    fm, body = read_entity(repo / "projects" / "demo" / "mvp" / "EPIC.md")
    assert fm["state"] == "completed"
    assert "State changed from active to completed" in body


def test_project_set_status_invalid_state(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "set-status", "demo", "unknown", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 2  # Click usage error
    assert "unknown" in result.output


def test_project_set_status_missing_project(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "set-status", "missing", "paused", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
