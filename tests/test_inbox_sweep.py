from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.scopes import iter_epic_dirs


def _repo_with_project_and_epic(tmp_path: Path) -> Path:
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
    project = runner.invoke(
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
    assert project.exit_code == 0
    epic = runner.invoke(
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
    assert epic.exit_code == 0
    return tmp_path


def _write_inbox_item(path: Path, *, item_id: str, title: str, status: str = "open") -> None:
    write_entity(
        path,
        frontmatter={
            "id": item_id,
            "title": title,
            "author": "alice",
            "scope": "epic",
            "status": status,
            "created": date.today().isoformat(),
            "resolved": None,
        },
        body=f"# {title}\n\n## Note\n\nSeed item.\n\n## Activity Log\n\n",
    )


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_inbox_add_list_and_resolve_for_epic(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")

    add = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Capture parser risk",
            "--note",
            "Parser flags need follow-up.",
        ],
        obj={"cwd": repo},
    )

    assert add.exit_code == 0
    assert f"projects/demo_app/mvp/inbox/IN-{today}-001-capture-parser-risk.md" in add.output
    inbox_path = repo / "projects" / "demo_app" / "mvp" / "inbox" / f"IN-{today}-001-capture-parser-risk.md"
    frontmatter, body = read_entity(inbox_path)
    assert frontmatter["status"] == "open"
    assert frontmatter["scope"] == "epic"
    assert "Parser flags need follow-up." in body

    listed = CliRunner().invoke(
        cli,
        ["inbox", "list", "--epic", "projects/demo_app/mvp"],
        obj={"cwd": repo},
    )
    assert listed.exit_code == 0
    assert f"IN-{today}-001 open Capture parser risk" in listed.output

    resolved = CliRunner().invoke(
        cli,
        ["inbox", "resolve", f"IN-{today}-001", "--resolver", "alice", "--note", "Filed follow-up task."],
        obj={"cwd": repo},
    )
    assert resolved.exit_code == 0

    frontmatter, body = read_entity(inbox_path)
    assert frontmatter["status"] == "resolved"
    assert frontmatter["resolved"] == date.today().isoformat()
    assert "Resolved by alice. Filed follow-up task." in body


def test_inbox_add_requires_one_scope(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--author",
            "alice",
            "--title",
            "No scope",
            "--note",
            "Missing scope.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "exactly one of --project or --epic is required" in result.output


def test_inbox_resolve_rejects_non_inbox_direct_path_without_modifying_project(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    project_path = repo / "projects" / "demo_app" / "PROJECT.md"
    original_project_text = project_path.read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "inbox",
            "resolve",
            "projects/demo_app/PROJECT.md",
            "--resolver",
            "alice",
            "--note",
            "Do not rewrite project metadata.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "inbox item 'projects/demo_app/PROJECT.md' not found" in result.output
    assert project_path.read_text(encoding="utf-8") == original_project_text


def test_inbox_resolve_rejects_direct_path_outside_official_inboxes(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")
    stray_path = repo / "docs" / "inbox" / f"IN-{today}-001-note.md"
    _write_inbox_item(stray_path, item_id=f"IN-{today}-001", title="Stray note")
    original_text = stray_path.read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "inbox",
            "resolve",
            f"docs/inbox/IN-{today}-001-note.md",
            "--resolver",
            "alice",
            "--note",
            "Must not touch arbitrary inbox folders.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "inbox item" in result.output
    assert "not found" in result.output
    assert stray_path.read_text(encoding="utf-8") == original_text


def test_inbox_resolve_accepts_project_inbox_direct_path(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")

    add = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--project",
            "demo_app",
            "--author",
            "alice",
            "--title",
            "Project direct path",
            "--note",
            "Project direct path should resolve.",
        ],
        obj={"cwd": repo},
    )
    assert add.exit_code == 0

    resolved = CliRunner().invoke(
        cli,
        [
            "inbox",
            "resolve",
            f"projects/demo_app/inbox/IN-{today}-001-project-direct-path.md",
            "--resolver",
            "alice",
            "--note",
            "Resolved by direct path.",
        ],
        obj={"cwd": repo},
    )

    assert resolved.exit_code == 0
    inbox_path = repo / "projects" / "demo_app" / "inbox" / f"IN-{today}-001-project-direct-path.md"
    frontmatter, body = read_entity(inbox_path)
    assert frontmatter["status"] == "resolved"
    assert "Resolved by alice. Resolved by direct path." in body


def test_inbox_resolve_rejects_official_inbox_non_markdown_direct_path(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")
    non_markdown_path = repo / "projects" / "demo_app" / "inbox" / f"IN-{today}-004-official-non-md.txt"
    _write_inbox_item(non_markdown_path, item_id=f"IN-{today}-004", title="Official non markdown")
    original_text = non_markdown_path.read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "inbox",
            "resolve",
            f"projects/demo_app/inbox/IN-{today}-004-official-non-md.txt",
            "--resolver",
            "alice",
            "--note",
            "Must reject non-markdown files.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "inbox item" in result.output
    assert "not found" in result.output
    assert non_markdown_path.read_text(encoding="utf-8") == original_text


def test_inbox_resolve_accepts_epic_inbox_direct_path(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")

    add = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Epic direct path",
            "--note",
            "Epic direct path should resolve.",
        ],
        obj={"cwd": repo},
    )
    assert add.exit_code == 0

    resolved = CliRunner().invoke(
        cli,
        [
            "inbox",
            "resolve",
            f"projects/demo_app/mvp/inbox/IN-{today}-001-epic-direct-path.md",
            "--resolver",
            "alice",
            "--note",
            "Resolved by direct path.",
        ],
        obj={"cwd": repo},
    )

    assert resolved.exit_code == 0
    inbox_path = repo / "projects" / "demo_app" / "mvp" / "inbox" / f"IN-{today}-001-epic-direct-path.md"
    frontmatter, body = read_entity(inbox_path)
    assert frontmatter["status"] == "resolved"
    assert "Resolved by alice. Resolved by direct path." in body


def test_inbox_add_uses_max_sequence_for_today(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")
    inbox_path = repo / "projects" / "demo_app" / "mvp" / "inbox"
    _write_inbox_item(
        inbox_path / f"IN-{today}-001-first.md",
        item_id=f"IN-{today}-001",
        title="First",
    )
    _write_inbox_item(
        inbox_path / f"IN-{today}-003-third.md",
        item_id=f"IN-{today}-003",
        title="Third",
    )

    result = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Fill gap safely",
            "--note",
            "Do not reuse existing IDs.",
        ],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert f"projects/demo_app/mvp/inbox/IN-{today}-004-fill-gap-safely.md" in result.output
    assert (inbox_path / f"IN-{today}-003-third.md").is_file()


def test_inbox_resolve_rejects_already_resolved_item_without_duplicate_activity(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")

    add = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Resolve once",
            "--note",
            "Only one resolution entry.",
        ],
        obj={"cwd": repo},
    )
    assert add.exit_code == 0
    item_ref = f"IN-{today}-001"
    item_path = repo / "projects" / "demo_app" / "mvp" / "inbox" / f"{item_ref}-resolve-once.md"

    first = CliRunner().invoke(
        cli,
        ["inbox", "resolve", item_ref, "--resolver", "alice", "--note", "Filed follow-up task."],
        obj={"cwd": repo},
    )
    assert first.exit_code == 0

    second = CliRunner().invoke(
        cli,
        ["inbox", "resolve", item_ref, "--resolver", "alice", "--note", "Duplicate resolution."],
        obj={"cwd": repo},
    )

    assert second.exit_code == 1
    assert f"inbox item {item_ref} is not open" in second.output
    frontmatter, body = read_entity(item_path)
    assert frontmatter["status"] == "resolved"
    assert body.count("Resolved by alice.") == 1
    assert "Duplicate resolution." not in body


def test_inbox_resolve_ignores_malformed_prefix_match(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")
    item_ref = f"IN-{today}-001"
    malformed_path = repo / "projects" / "demo_app" / "mvp" / "inbox" / f"{item_ref}-bad_slug.md"
    _write_inbox_item(malformed_path, item_id=item_ref, title="Bad slug")

    result = CliRunner().invoke(
        cli,
        ["inbox", "resolve", item_ref, "--resolver", "alice", "--note", "Should not match."],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert f"inbox item '{item_ref}' not found" in result.output
    frontmatter, body = read_entity(malformed_path)
    assert frontmatter["status"] == "open"
    assert "Should not match." not in body


def test_inbox_add_list_for_project_scope(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    today = date.today().strftime("%Y%m%d")

    add = CliRunner().invoke(
        cli,
        [
            "inbox",
            "add",
            "--project",
            "demo_app",
            "--author",
            "alice",
            "--title",
            "Project-level note",
            "--note",
            "Applies before an epic exists.",
        ],
        obj={"cwd": repo},
    )

    assert add.exit_code == 0
    assert f"projects/demo_app/inbox/IN-{today}-001-project-level-note.md" in add.output
    inbox_path = repo / "projects" / "demo_app" / "inbox" / f"IN-{today}-001-project-level-note.md"
    frontmatter, body = read_entity(inbox_path)
    assert frontmatter["scope"] == "project"
    assert frontmatter["status"] == "open"
    assert "Applies before an epic exists." in body

    listed = CliRunner().invoke(
        cli,
        ["inbox", "list", "--project", "demo_app"],
        obj={"cwd": repo},
    )
    assert listed.exit_code == 0
    assert f"IN-{today}-001 open Project-level note" in listed.output


def test_iter_epic_dirs_rejects_projects_path_that_is_not_a_directory(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "projects").write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(TrailmindError, match="projects path .* is not a directory"):
        iter_epic_dirs(tmp_path)


def test_sweep_reports_ready_blocked_missing_deliverables_and_open_inbox(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    parser = runner.invoke(
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
            "Build parser",
        ],
        obj={"cwd": repo},
    )
    assert parser.exit_code == 0
    ui = runner.invoke(
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
            "Build UI",
            "--depends-on",
            "T-123456-001",
            "--deliverables",
            "screenshots attached",
        ],
        obj={"cwd": repo},
    )
    assert ui.exit_code == 0
    inbox = runner.invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Capture release risk",
            "--note",
            "Need release notes.",
        ],
        obj={"cwd": repo},
    )
    assert inbox.exit_code == 0

    result = runner.invoke(cli, ["sweep", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "Project Automation Sweep" in result.output
    assert "Ready" in result.output
    assert "T-123456-001 Build parser" in result.output
    assert "projects/demo_app/mvp/tasks/T-123456-001-build-parser.md" in result.output
    assert "Blocked" in result.output
    assert "T-123456-002 Build UI" in result.output
    assert "projects/demo_app/mvp/tasks/T-123456-002-build-ui.md" in result.output
    assert "unsatisfied: T-123456-001" in result.output
    assert "Missing deliverables" in result.output
    assert "screenshots attached" in result.output
    assert "Open inbox" in result.output
    assert "Capture release risk" in result.output
    assert f"projects/demo_app/mvp/inbox/IN-{date.today():%Y%m%d}-001-capture-release-risk.md" in result.output


def test_sweep_rejects_multiple_scope_flags_without_traceback(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["sweep", "--project", "demo_app", "--epic", "projects/demo_app/mvp"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "sweep accepts only one scope flag" in result.output


def test_sweep_project_output_includes_paths_for_duplicate_inbox_ids(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    second_epic = runner.invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "api",
            "--title",
            "API",
            "--goal",
            "Backend release",
        ],
        obj={"cwd": repo},
    )
    assert second_epic.exit_code == 0
    first = runner.invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Duplicate risk",
            "--note",
            "MVP risk.",
        ],
        obj={"cwd": repo},
    )
    assert first.exit_code == 0
    second = runner.invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/api",
            "--author",
            "alice",
            "--title",
            "Duplicate risk",
            "--note",
            "API risk.",
        ],
        obj={"cwd": repo},
    )
    assert second.exit_code == 0

    result = runner.invoke(cli, ["sweep", "--project", "demo_app"], obj={"cwd": repo})

    today = date.today().strftime("%Y%m%d")
    assert result.exit_code == 0
    assert f"IN-{today}-001 Duplicate risk (projects/demo_app/api/inbox/IN-{today}-001-duplicate-risk.md)" in result.output
    assert f"IN-{today}-001 Duplicate risk (projects/demo_app/mvp/inbox/IN-{today}-001-duplicate-risk.md)" in result.output


def test_sweep_rejects_tasks_path_that_is_not_a_directory_without_traceback(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    tasks_path = repo / "projects" / "demo_app" / "mvp" / "tasks"
    tasks_path.rmdir()
    tasks_path.write_text("not a directory\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["sweep", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert f"tasks path {tasks_path} is not a directory" in result.output


def test_sweep_reports_stale_task_at_cutoff(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    add = runner.invoke(
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
            "Old task",
        ],
        obj={"cwd": repo},
    )
    assert add.exit_code == 0
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-old-task.md"
    frontmatter, body = read_entity(task_path)
    frontmatter["created"] = "2000-01-01"
    body = body.replace(date.today().isoformat(), "2000-01-01")
    write_entity(task_path, frontmatter=frontmatter, body=body)

    result = runner.invoke(
        cli,
        ["sweep", "--epic", "projects/demo_app/mvp", "--stale-days", "7"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    assert "Stale" in result.output
    assert "T-123456-001 Old task" in result.output
    assert "projects/demo_app/mvp/tasks/T-123456-001-old-task.md" in result.output


def test_sweep_stale_days_must_be_positive(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["sweep", "--epic", "projects/demo_app/mvp", "--stale-days", "0"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "Invalid value for '--stale-days'" in result.output


def test_sweep_is_read_only(tmp_path: Path):
    repo = _repo_with_project_and_epic(tmp_path)
    runner = CliRunner()
    add_task = runner.invoke(
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
            "Read only task",
        ],
        obj={"cwd": repo},
    )
    assert add_task.exit_code == 0
    add_inbox = runner.invoke(
        cli,
        [
            "inbox",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--author",
            "alice",
            "--title",
            "Read only inbox",
            "--note",
            "Do not mutate.",
        ],
        obj={"cwd": repo},
    )
    assert add_inbox.exit_code == 0
    before = _file_snapshot(repo)

    result = runner.invoke(cli, ["sweep", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert _file_snapshot(repo) == before
