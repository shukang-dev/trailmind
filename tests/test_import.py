import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.importer import import_repo, load_export_file


def _make_export_data() -> dict:
    return {
        "roster": [
            {"email": "alice@example.com", "shortname": "alice", "uid": "123456", "name": "Alice"},
        ],
        "projects": [
            {
                "slug": "demo",
                "title": "Demo Project",
                "goal": "Test import.",
                "state": "active",
                "owners": ["alice@example.com"],
                "tags": ["test"],
                "created": "2026-07-03",
                "path": "projects/demo",
                "body": "# Demo\n\nTest.",
                "inbox": [],
                "epics": [
                    {
                        "slug": "mvp",
                        "title": "MVP",
                        "goal": "First release.",
                        "state": "active",
                        "start": "2026-07-01",
                        "target": "2026-07-31",
                        "roster": ["alice"],
                        "repos": ["demo"],
                        "created": "2026-07-03",
                        "path": "projects/demo/mvp",
                        "body": "# MVP\n\nTesting.",
                        "tasks": [
                            {
                                "id": "T-123456-001",
                                "title": "Test Task",
                                "status": "created",
                                "filer": "alice",
                                "owner": "alice",
                                "created": "2026-07-03",
                                "code_paths": ["src/app.py"],
                                "deliverables": ["tests pass"],
                                "completed_deliverables": [],
                                "depends_on": [],
                                "soft_depends_on": [],
                                "known_issues": [],
                                "path": "projects/demo/mvp/tasks/T-123456-001-test-task.md",
                                "body": "# Test Task\n\nScope.\n",
                            },
                        ],
                        "issues": [
                            {
                                "id": "I-123456-001",
                                "title": "Test Issue",
                                "status": "open",
                                "severity": "high",
                                "filer": "alice",
                                "created": "2026-07-03",
                                "linked_tasks": [],
                                "path": "projects/demo/mvp/issues/I-123456-001-test-issue.md",
                                "body": "# Test Issue\n\nDesc.\n",
                            },
                        ],
                        "milestones": [
                            {
                                "id": "M-001",
                                "title": "Alpha",
                                "status": "created",
                                "date": "2026-07-15",
                                "created": "2026-07-03",
                                "path": "projects/demo/mvp/milestones/M-001-alpha.md",
                                "body": "# Alpha\n\n",
                            },
                        ],
                        "inbox": [
                            {
                                "id": "IN-20260703-001",
                                "title": "Test Inbox",
                                "status": "open",
                                "author": "alice",
                                "scope": "epic",
                                "created": "2026-07-03",
                                "resolved": None,
                                "path": "projects/demo/mvp/inbox/IN-20260703-001-test-inbox.md",
                                "body": "# Test Inbox\n\nNote.\n",
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _write_export(tmp_path: Path, data: dict) -> Path:
    export_path = tmp_path / "export.json"
    export_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return export_path


def test_import_creates_project_and_epic(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    export_file = _write_export(tmp_path, data)

    created = import_repo(tmp_path, data)

    # Check that files were created
    paths = [p.relative_to(tmp_path).as_posix() for p in created]
    assert "projects/demo/PROJECT.md" in paths
    assert "projects/demo/mvp/EPIC.md" in paths


def test_import_creates_tasks(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    import_repo(tmp_path, data)

    task_files = list((tmp_path / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    assert len(task_files) == 1
    assert "Test Task" in task_files[0].read_text()


def test_import_creates_issues(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    import_repo(tmp_path, data)

    issue_files = list((tmp_path / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))
    assert len(issue_files) == 1


def test_import_creates_milestones(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    import_repo(tmp_path, data)

    ms_files = list((tmp_path / "projects" / "demo" / "mvp" / "milestones").glob("M-*.md"))
    assert len(ms_files) == 1


def test_import_is_idempotent(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()

    first = import_repo(tmp_path, data)
    second = import_repo(tmp_path, data)

    # Second import should not create new files (they already exist)
    assert len(second) == 0


def test_import_force_overwrites(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()

    first = import_repo(tmp_path, data)
    second = import_repo(tmp_path, data, force=True)

    # With force, all files are recreated
    assert len(second) == len(first)


def test_import_updates_roster(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    import_repo(tmp_path, data)

    import yaml
    roster = yaml.safe_load((tmp_path / "roster.yaml").read_text())
    assert len(roster["developers"]) == 1
    assert roster["developers"][0]["email"] == "alice@example.com"


def test_import_roster_appends(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    import yaml
    (tmp_path / "roster.yaml").write_text(
        yaml.safe_dump({"developers": [
            {"email": "existing@example.com", "shortname": "existing", "uid": "999", "name": "Existing"},
        ]}),
        encoding="utf-8",
    )
    data = _make_export_data()
    import_repo(tmp_path, data)

    roster = yaml.safe_load((tmp_path / "roster.yaml").read_text())
    assert len(roster["developers"]) == 2


def test_load_export_file_invalid_json(tmp_path: Path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json", encoding="utf-8")

    from trailmind.errors import TrailmindError
    try:
        load_export_file(bad_file)
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "invalid JSON" in str(exc)


def test_load_export_file_missing(tmp_path: Path):
    from trailmind.errors import TrailmindError
    try:
        load_export_file(tmp_path / "missing.json")
        assert False, "Should have raised"
    except TrailmindError as exc:
        assert "not found" in str(exc)


def test_import_cli(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    export_file = _write_export(tmp_path, data)

    result = CliRunner().invoke(cli, ["import", str(export_file)], obj={"cwd": tmp_path})
    assert result.exit_code == 0
    assert "PROJECT.md" in result.output
    assert "Imported" in result.output


def test_import_cli_idempotent(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    export_file = _write_export(tmp_path, data)
    runner = CliRunner()

    runner.invoke(cli, ["import", str(export_file)], obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["import", str(export_file)], obj={"cwd": tmp_path})

    assert result.exit_code == 0
    assert "already exist" in result.output


def test_import_cli_force(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    data = _make_export_data()
    export_file = _write_export(tmp_path, data)
    runner = CliRunner()

    runner.invoke(cli, ["import", str(export_file)], obj={"cwd": tmp_path})
    result = runner.invoke(cli, ["import", str(export_file), "--force"], obj={"cwd": tmp_path})

    assert result.exit_code == 0
    assert "Imported" in result.output


def test_export_import_roundtrip(tmp_path: Path):
    """Export then import should produce the same data."""
    from trailmind.export import export_repo

    # Set up initial repo
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "roundtrip", "--title", "Roundtrip", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "roundtrip", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "roundtrip"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/roundtrip/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Roundtrip Task"], obj={"cwd": tmp_path})

    # Export
    exported = export_repo(tmp_path)
    assert len(exported["projects"]) == 1

    # Import into a fresh repo
    new_repo = tmp_path / "new_repo"
    new_repo.mkdir()
    (new_repo / ".git").mkdir()
    created = import_repo(new_repo, exported)

    # Verify
    assert any("PROJECT.md" in str(p) for p in created)
    assert any("EPIC.md" in str(p) for p in created)
    assert any("T-" in str(p) for p in created)
