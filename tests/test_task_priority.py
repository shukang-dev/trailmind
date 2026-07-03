from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.task import DEFAULT_PRIORITY, TASK_PRIORITIES, validate_task_priority


def _repo_with_task(tmp_path: Path, priority: str | None = None) -> tuple[Path, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    add_args = ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task"]
    if priority:
        add_args.extend(["--priority", priority])
    result = runner.invoke(cli, add_args, obj={"cwd": tmp_path})
    assert result.exit_code == 0
    task_path = tmp_path / "projects" / "demo" / "test" / "tasks"
    task_files = sorted(task_path.glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id


def test_task_add_default_priority(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["priority"] == DEFAULT_PRIORITY


def test_task_add_with_priority(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path, priority="high")
    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["priority"] == "high"


def test_task_add_with_critical_priority(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path, priority="critical")
    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["priority"] == "critical"


def test_validate_task_priority_valid():
    for p in TASK_PRIORITIES:
        assert validate_task_priority(p) == p


def test_validate_task_priority_case_insensitive():
    assert validate_task_priority("HIGH") == "high"
    assert validate_task_priority("Low") == "low"


def test_validate_task_priority_invalid():
    from trailmind.errors import TrailmindError
    try:
        validate_task_priority("urgent")
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "invalid task priority" in str(exc)


def test_task_set_priority_cli(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path, priority="medium")
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "set-priority", task_id, "high", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["priority"] == "high"
    assert "Priority changed from medium to high" in body


def test_task_set_priority_with_note(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path, priority="low")
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "set-priority", task_id, "critical", "--actor", "alice", "--note", "Production issue"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["priority"] == "critical"
    assert "Production issue" in body


def test_task_set_priority_invalid_is_user_facing(tmp_path: Path):
    repo, task_id = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "set-priority", task_id, "urgent", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 2  # Click usage error
    assert "urgent" in result.output
