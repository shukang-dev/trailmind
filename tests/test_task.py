from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.task import split_csv


def _repo_with_epic(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n"
        "  shortname: alice\n"
        "  uid: '123456'\n"
        "  name: Alice\n",
        encoding="utf-8",
    )
    epic = tmp_path / "projects" / "demo_app" / "mvp"
    (epic / "tasks").mkdir(parents=True)
    (epic / "EPIC.md").write_text(
        "---\n"
        "slug: mvp\n"
        "title: MVP\n"
        "project: demo_app\n"
        "---\n"
        "# MVP\n",
        encoding="utf-8",
    )
    return tmp_path


def _add_task(repo: Path, title: str = "Build Login Flow", extra_args: list[str] | None = None):
    args = [
        "task",
        "add",
        "--epic",
        "projects/demo_app/mvp",
        "--filer",
        "alice@example.com",
        "--owner",
        "alice@example.com",
        "--title",
        title,
        "--code-paths",
        "src/app.py, tests/test_app.py",
        "--depends-on",
        "",
        "--soft-depends-on",
        " , ",
    ]
    if extra_args:
        args.extend(extra_args)
    return CliRunner().invoke(
        cli,
        args,
        obj={"cwd": repo},
    )


def _update_task_status(repo: Path, status: str = "in_progress"):
    return CliRunner().invoke(
        cli,
        ["task", "update", "T-123456-001", "--status", status],
        obj={"cwd": repo},
    )


def test_task_add_creates_task(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = _add_task(repo)

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output

    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    assert task_path.exists()

    frontmatter, body = read_entity(task_path)
    assert frontmatter["id"] == "T-123456-001"
    assert frontmatter["title"] == "Build Login Flow"
    assert frontmatter["filer"] == "alice"
    assert frontmatter["owner"] == "alice"
    assert frontmatter["status"] == "created"
    assert date.fromisoformat(frontmatter["created"])
    assert frontmatter["start"] is None
    assert frontmatter["due"] is None
    assert frontmatter["branches"] == {}
    assert frontmatter["verify"] == {}
    assert frontmatter["code_paths"] == ["src/app.py", "tests/test_app.py"]
    assert frontmatter["design_doc"] is None
    assert frontmatter["depends_on"] == []
    assert frontmatter["soft_depends_on"] == []
    assert frontmatter["known_issues"] == []
    assert frontmatter["deliverables"] == []
    assert frontmatter["completed_deliverables"] == []
    assert "## Scope" in body
    assert "## Acceptance" in body
    assert "## Activity Log" in body


def test_task_add_writes_design_doc_when_specified(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = _add_task(repo, extra_args=["--design-doc", "docs/specs/parser.md"])

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, _body = read_entity(task_path)
    assert frontmatter["design_doc"] == "docs/specs/parser.md"


def test_task_update_status(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = _update_task_status(repo)

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    assert frontmatter["status"] == "in_progress"
    assert "Status changed from created to in_progress by trailmind." in body


def test_task_set_status_validates_transition_and_logs(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "set-status",
            "T-123456-001",
            "ready",
            "--actor",
            "alice",
            "--note",
            "Ready for implementation.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    assert frontmatter["status"] == "ready"
    assert "Status changed from created to ready by alice. Ready for implementation." in body


def test_task_set_status_rejects_invalid_transition(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "done", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid task status transition" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["task", "update", "T-123456-001", "--status", "done"],
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
    ],
)
def test_task_status_commands_handle_unreadable_task_files_as_user_errors(tmp_path: Path, args: list[str]):
    repo = _repo_with_epic(tmp_path)
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-bad.md"
    task_path.write_bytes(b"\xff\xfe\x00not utf-8")

    result = CliRunner().invoke(
        cli,
        args,
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.output
    assert "could not read task file" in result.output
    assert "Traceback" not in result.output


def test_task_close_marks_done_and_logs(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    update_result = _update_task_status(repo)
    assert update_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Shipped login flow."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    assert frontmatter["status"] == "done"
    assert "Shipped login flow." in body
    assert body.index("## Activity Log") < body.index("Shipped login flow.")


def test_task_close_rejects_invalid_transition_from_created(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid task status transition" in result.output
    assert "Traceback" not in result.output


def test_task_close_sanitizes_multiline_note_before_logging(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    update_result = _update_task_status(repo)
    assert update_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "done\n## Injected\ntext"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert result.exception is None
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    _frontmatter, body = read_entity(task_path)
    activity_line = next(line for line in body.splitlines() if "Closed by alice" in line)
    assert activity_line.endswith("done ## Injected text")
    assert "\n## Injected\n" not in body


def test_task_close_sanitizes_multiline_closer_before_logging(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    update_result = _update_task_status(repo)
    assert update_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice\n## Injected", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert result.exception is None
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    _frontmatter, body = read_entity(task_path)
    activity_lines = [
        line
        for line in body.splitlines()[body.splitlines().index("## Activity Log") + 1 :]
        if line.strip()
    ]
    closed_lines = [line for line in activity_lines if "Closed by alice ## Injected" in line]
    assert closed_lines == [f"- {date.today().isoformat()}: Closed by alice ## Injected. Done."]
    assert all(line.startswith("- ") for line in activity_lines)
    assert "\n## Injected" not in body


def test_task_close_rejects_blank_closer(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    update_result = _update_task_status(repo)
    assert update_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", " \n\t", "--note", "Done."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "activity actor is required" in result.output
    assert "Traceback" not in result.output


def test_task_update_invalid_status_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "update", "T-123456-001", "--status", "bogus"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid task status" in result.output
    assert "Traceback" not in result.output


def test_task_add_unknown_filer_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "missing@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "missing@example.com is not registered in roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_task_add_when_tasks_path_is_file_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    tasks_path.rmdir()
    tasks_path.write_text("not a directory\n", encoding="utf-8")

    result = _add_task(repo)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.output
    assert "tasks path" in result.output
    assert "not a directory" in result.output
    assert "Traceback" not in result.output


def test_task_add_unknown_owner_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "missing@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "missing@example.com is not registered in roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_task_add_missing_epic_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/missing",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "epic projects/demo_app/missing does not exist" in result.output
    assert "Traceback" not in result.output


def test_task_normalize_statuses_reports_legacy_statuses_without_writing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    frontmatter["status"] = "planned"
    from trailmind.entity_io import write_entity

    write_entity(task_path, frontmatter=frontmatter, body=body)

    result = CliRunner().invoke(cli, ["task", "normalize-statuses"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "T-123456-001 planned -> created" in result.output
    reread_frontmatter, _body = read_entity(task_path)
    assert reread_frontmatter["status"] == "planned"


def test_task_normalize_statuses_writes_legacy_statuses_when_requested(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    add_result = _add_task(repo)
    assert add_result.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    frontmatter, body = read_entity(task_path)
    frontmatter["status"] = "integration"
    from trailmind.entity_io import write_entity

    write_entity(task_path, frontmatter=frontmatter, body=body)

    result = CliRunner().invoke(cli, ["task", "normalize-statuses", "--write"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "T-123456-001 integration -> in_progress" in result.output
    reread_frontmatter, _body = read_entity(task_path)
    assert reread_frontmatter["status"] == "in_progress"


def test_task_normalize_statuses_write_does_not_partially_update_when_later_task_is_invalid(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    first_add_result = _add_task(repo)
    assert first_add_result.exit_code == 0
    second_add_result = _add_task(repo, title="Build Logout Flow")
    assert second_add_result.exit_code == 0
    first_task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    second_task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-002-build-logout-flow.md"
    first_frontmatter, first_body = read_entity(first_task_path)
    second_frontmatter, second_body = read_entity(second_task_path)
    first_frontmatter["status"] = "planned"
    second_frontmatter["status"] = "paused"
    from trailmind.entity_io import write_entity

    write_entity(first_task_path, frontmatter=first_frontmatter, body=first_body)
    write_entity(second_task_path, frontmatter=second_frontmatter, body=second_body)

    result = CliRunner().invoke(cli, ["task", "normalize-statuses", "--write"], obj={"cwd": repo})

    assert result.exit_code == 1
    assert "invalid task status" in result.output
    assert "Traceback" not in result.output
    reread_first_frontmatter, _body = read_entity(first_task_path)
    assert reread_first_frontmatter["status"] == "planned"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        (" , ", []),
        ("src/app.py, tests/test_app.py", ["src/app.py", "tests/test_app.py"]),
        (" first , second ,, third ", ["first", "second", "third"]),
    ],
)
def test_split_csv_trims_and_drops_empty_entries(value: str, expected: list[str]):
    assert split_csv(value) == expected


def test_task_list_cli(tmp_path: Path):
    from click.testing import CliRunner
    from trailmind.cli import cli

    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task"], obj={"cwd": tmp_path})

    result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test"], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "Test Task" in result.output

    json_result = runner.invoke(cli, ["task", "list", "--epic", "projects/demo/test", "--json"], obj={"cwd": tmp_path})
    assert json_result.exit_code == 0
    import json
    data = json.loads(json_result.output)
    assert len(data) == 1
    assert data[0]["title"] == "Test Task"
    assert data[0]["status"] == "created"
