from datetime import date
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


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
