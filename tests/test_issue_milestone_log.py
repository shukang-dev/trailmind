from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

import trailmind.issue as issue_module
import trailmind.log as log_module
from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity


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
    runner = CliRunner()
    project_result = runner.invoke(
        cli,
        [
            "project",
            "init",
            "--slug",
            "demo_app",
            "--title",
            "Demo App",
            "--goal",
            "Build a useful demo.",
        ],
        obj={"cwd": tmp_path},
    )
    assert project_result.exit_code == 0
    epic_result = runner.invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "mvp",
            "--title",
            "MVP",
            "--goal",
            "First usable release",
        ],
        obj={"cwd": tmp_path},
    )
    assert epic_result.exit_code == 0
    return tmp_path


def _add_second_epic(repo: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "next",
            "--title",
            "Next",
            "--goal",
            "Follow-up release",
        ],
        obj={"cwd": repo},
    )
    assert result.exit_code == 0


def _add_task(repo: Path):
    return CliRunner().invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build Login Flow",
        ],
        obj={"cwd": repo},
    )


def _add_issue(repo: Path, title: str = "Login Fails", epic: str = "projects/demo_app/mvp"):
    return CliRunner().invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            epic,
            "--filer",
            "alice@example.com",
            "--title",
            title,
            "--description",
            "Users cannot sign in.",
            "--severity",
            "high",
        ],
        obj={"cwd": repo},
    )


def _move_task_to_in_progress(repo: Path):
    return CliRunner().invoke(
        cli,
        ["task", "set-status", "T-123456-001", "in_progress", "--actor", "alice"],
        obj={"cwd": repo},
    )


def _login_task_path(repo: Path) -> Path:
    return repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"


def test_issue_add_link_close_and_log(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0
    assert "projects/demo_app/mvp/issues/I-123456-001-login-fails.md" in issue_result.output

    link_result = CliRunner().invoke(
        cli,
        ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    assert "projects/demo_app/mvp/issues/I-123456-001-login-fails.md" in link_result.output
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in link_result.output

    log_result = CliRunner().invoke(
        cli,
        ["log", "I-123456-001", "--author", "alice", "--note", "Investigated root cause."],
        obj={"cwd": repo},
    )
    assert log_result.exit_code == 0

    close_result = CliRunner().invoke(
        cli,
        [
            "issue",
            "close",
            "I-123456-001",
            "--closer",
            "alice",
            "--status",
            "done",
            "--note",
            "Fixed by login patch.",
        ],
        obj={"cwd": repo},
    )
    assert close_result.exit_code == 0

    issue_path = repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-001-login-fails.md"
    issue_frontmatter, issue_body = read_entity(issue_path)
    assert issue_frontmatter["status"] == "done"
    assert issue_frontmatter["linked_tasks"] == ["T-123456-001"]
    assert "## Activity Log" in issue_body
    assert "Investigated root cause." in issue_body
    assert "Fixed by login patch." in issue_body

    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-login-flow.md"
    task_frontmatter, _task_body = read_entity(task_path)
    assert task_frontmatter["known_issues"] == ["I-123456-001"]


def test_issue_carry_adds_links(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _add_second_epic(repo)
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["issue", "carry", "--issue", "I-123456-001", "--to-epic", "projects/demo_app/next"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    source_issue = "projects/demo_app/mvp/issues/I-123456-001-login-fails.md"
    assert source_issue in result.output
    assert "projects/demo_app/next/EPIC.md" in result.output

    issue_frontmatter, _issue_body = read_entity(repo / source_issue)
    assert issue_frontmatter["carried_into"] == ["projects/demo_app/next"]

    target_frontmatter, _target_body = read_entity(repo / "projects" / "demo_app" / "next" / "EPIC.md")
    assert target_frontmatter["carried_issues"] == [source_issue]


def test_milestone_add(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "milestone",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--title",
            "Beta Freeze",
            "--date",
            "2026-07-15",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/milestones/M-001-beta-freeze.md" in result.output
    milestone_path = repo / "projects" / "demo_app" / "mvp" / "milestones" / "M-001-beta-freeze.md"
    frontmatter, body = read_entity(milestone_path)
    assert frontmatter["id"] == "M-001"
    assert frontmatter["date"] == "2026-07-15"
    assert frontmatter["status"] == "planned"
    assert date.fromisoformat(frontmatter["created"])
    assert "Beta Freeze" in body
    assert "2026-07-15" in body


def test_issue_close_invalid_status_is_user_facing(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        [
            "issue",
            "close",
            "I-123456-001",
            "--closer",
            "alice",
            "--status",
            "bogus",
            "--note",
            "Not valid.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "invalid issue close status" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("args", "expected_fragment"),
    [
        (["--author", "alice\n## Injected", "--note", "Reviewed."], "Note by alice ## Injected. Reviewed."),
        (["--author", "alice", "--note", "Reviewed.\n## Injected"], "Note by alice. Reviewed. ## Injected"),
    ],
)
def test_generic_log_multiline_author_or_note_is_collapsed_without_heading_injection(
    tmp_path: Path, args: list[str], expected_fragment: str
):
    repo = _repo_with_epic(tmp_path)
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["log", "I-123456-001", *args],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert result.exception is None
    _frontmatter, body = read_entity(
        repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-001-login-fails.md"
    )
    activity_line = next(line for line in body.splitlines() if "Note by" in line)
    assert activity_line == f"- {date.today().isoformat()}: {expected_fragment}"
    assert "\n## Injected" not in body


def test_generic_log_rejects_blank_author(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["log", "I-123456-001", "--author", " \t", "--note", "Reviewed."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "activity actor is required" in result.output
    assert "Traceback" not in result.output


def test_public_helpers_accept_requested_keyword_names(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _add_second_epic(repo)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0

    linked_paths = issue_module.link_issue(repo, raw_issue="I-123456-001", raw_task="T-123456-001")
    assert [path.relative_to(repo).as_posix() for path in linked_paths] == [
        "projects/demo_app/mvp/issues/I-123456-001-login-fails.md",
        "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md",
    ]

    issue_path = log_module.append_log(
        repo,
        raw_id="I-123456-001",
        entity="I",
        author="alice",
        note="Checked via helper.",
    )
    assert issue_path.relative_to(repo).as_posix() == "projects/demo_app/mvp/issues/I-123456-001-login-fails.md"

    closed_path = issue_module.close_issue(
        repo,
        raw_id="I-123456-001",
        closer="alice",
        status="done",
        note="Closed via helper.",
    )
    assert closed_path == issue_path

    carried_paths = issue_module.carry_issue(repo, raw_issue="I-123456-001", to_epic="projects/demo_app/next")
    assert [path.relative_to(repo).as_posix() for path in carried_paths] == [
        "projects/demo_app/mvp/issues/I-123456-001-login-fails.md",
        "projects/demo_app/next/EPIC.md",
    ]

    frontmatter, body = read_entity(issue_path)
    assert frontmatter["status"] == "done"
    assert frontmatter["linked_tasks"] == ["T-123456-001"]
    assert frontmatter["carried_into"] == ["projects/demo_app/next"]
    assert "Checked via helper." in body
    assert "Closed via helper." in body


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (["log", "I-123456-001", "--author", "alice", "--note", "Reviewed."], "could not read issue file"),
        (
            [
                "issue",
                "close",
                "I-123456-001",
                "--closer",
                "alice",
                "--status",
                "done",
                "--note",
                "Closed.",
            ],
            "could not read issue file",
        ),
    ],
)
def test_unreadable_issue_file_returns_user_facing_error(
    tmp_path: Path, command: list[str], message: str
):
    repo = _repo_with_epic(tmp_path)
    issue_path = repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-001-bad.md"
    issue_path.write_bytes(b"\xff\xfe\x00not utf-8")

    result = CliRunner().invoke(
        cli,
        command,
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert message in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("folder", "command", "message"),
    [
        (
            "issues",
            [
                "issue",
                "add",
                "--epic",
                "projects/demo_app/mvp",
                "--filer",
                "alice@example.com",
                "--title",
                "Login Fails",
                "--description",
                "Users cannot sign in.",
                "--severity",
                "high",
            ],
            "issues path",
        ),
        (
            "milestones",
            [
                "milestone",
                "add",
                "--epic",
                "projects/demo_app/mvp",
                "--title",
                "Beta Freeze",
                "--date",
                "2026-07-15",
            ],
            "milestones path",
        ),
    ],
)
def test_issue_and_milestone_add_when_folder_path_is_file_is_user_facing(
    tmp_path: Path, folder: str, command: list[str], message: str
):
    repo = _repo_with_epic(tmp_path)
    folder_path = repo / "projects" / "demo_app" / "mvp" / folder
    folder_path.rmdir()
    folder_path.write_text("not a directory\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        command,
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert message in result.output
    assert "not a directory" in result.output
    assert "Traceback" not in result.output


def test_task_close_reports_linked_open_issues(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0
    link_result = CliRunner().invoke(
        cli,
        ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    progress = _move_task_to_in_progress(repo)
    assert progress.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Task work complete."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output
    assert "linked open issues remain" in result.output
    assert "I-123456-001" in result.output


def test_task_close_does_not_report_closed_linked_issues(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0
    link_result = CliRunner().invoke(
        cli,
        ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    close_issue_result = CliRunner().invoke(
        cli,
        [
            "issue",
            "close",
            "I-123456-001",
            "--closer",
            "alice",
            "--status",
            "done",
            "--note",
            "Already fixed.",
        ],
        obj={"cwd": repo},
    )
    assert close_issue_result.exit_code == 0
    progress = _move_task_to_in_progress(repo)
    assert progress.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Task work complete."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output
    assert "linked open issues remain" not in result.output
    assert "I-123456-001" not in result.output


def test_task_close_warns_when_linked_issue_report_is_ambiguous(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0
    link_result = CliRunner().invoke(
        cli,
        ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    duplicate_issue_path = repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-001-duplicate.md"
    write_entity(
        duplicate_issue_path,
        frontmatter={
            "id": "I-123456-001",
            "title": "Duplicate Login Issue",
            "filer": "alice",
            "status": "open",
            "severity": "high",
            "created": date.today().isoformat(),
            "linked_tasks": ["T-123456-001"],
            "carried_into": [],
        },
        body="# Duplicate Login Issue\n",
    )
    progress = _move_task_to_in_progress(repo)
    assert progress.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Task work complete."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output
    assert "linked issue report skipped:" in result.output
    task_frontmatter, _task_body = read_entity(_login_task_path(repo))
    assert task_frontmatter["status"] == "done"


def test_task_close_warns_when_known_issues_is_malformed(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    progress = _move_task_to_in_progress(repo)
    assert progress.exit_code == 0
    task_path = _login_task_path(repo)
    task_frontmatter, task_body = read_entity(task_path)
    task_frontmatter["known_issues"] = "I-123456-001"
    write_entity(task_path, frontmatter=task_frontmatter, body=task_body)

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Task work complete."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-login-flow.md" in result.output
    assert "linked issue report skipped:" in result.output
    task_frontmatter, _task_body = read_entity(task_path)
    assert task_frontmatter["status"] == "done"


def test_task_close_reports_same_epic_linked_issue_when_duplicate_id_exists_elsewhere(tmp_path: Path):
    repo = _repo_with_epic(tmp_path)
    _add_second_epic(repo)
    task_result = _add_task(repo)
    assert task_result.exit_code == 0
    issue_result = _add_issue(repo)
    assert issue_result.exit_code == 0
    duplicate_issue_result = _add_issue(repo, title="Next Epic Login Fails", epic="projects/demo_app/next")
    assert duplicate_issue_result.exit_code == 0
    link_result = CliRunner().invoke(
        cli,
        [
            "issue",
            "link",
            "--issue",
            "projects/demo_app/mvp/issues/I-123456-001-login-fails.md",
            "--task",
            "T-123456-001",
        ],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    progress = _move_task_to_in_progress(repo)
    assert progress.exit_code == 0

    result = CliRunner().invoke(
        cli,
        ["task", "close", "T-123456-001", "--closer", "alice", "--note", "Task work complete."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "linked open issues remain: I-123456-001 Login Fails" in result.output
    assert "Next Epic Login Fails" not in result.output
