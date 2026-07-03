import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.export import export_repo, format_export


def _repo_with_data(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n"
        "  shortname: alice\n"
        "  uid: '123456'\n"
        "  name: Alice\n"
        "- email: bob@example.com\n"
        "  shortname: bob\n"
        "  uid: '654321'\n"
        "  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Testing.", "--owners", "alice@example.com", "--tags", "demo,test"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "mvp", "--title", "MVP", "--goal", "First release", "--roster", "alice,bob", "--repos", "demo"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task", "--code-paths", "src/app.py", "--deliverables", "tests pass"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com", "--title", "Test Issue", "--description", "Testing", "--severity", "high"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["milestone", "add", "--epic", "projects/demo/mvp", "--title", "Alpha", "--date", "2026-07-15"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["inbox", "add", "--epic", "projects/demo/mvp", "--author", "alice", "--title", "Test Inbox", "--note", "Testing inbox"], obj={"cwd": tmp_path})
    return tmp_path


def test_export_includes_roster(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    assert "roster" in data
    assert len(data["roster"]) == 2
    assert data["roster"][0]["email"] == "alice@example.com"


def test_export_includes_project(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    assert "projects" in data
    assert len(data["projects"]) == 1
    project = data["projects"][0]
    assert project["slug"] == "demo"
    assert project["title"] == "Demo"
    assert "test" in project["tags"]


def test_export_includes_epic(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    project = data["projects"][0]
    assert len(project["epics"]) == 1
    epic = project["epics"][0]
    assert epic["slug"] == "mvp"
    assert epic["title"] == "MVP"


def test_export_includes_tasks(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    epic = data["projects"][0]["epics"][0]
    assert len(epic["tasks"]) == 1
    task = epic["tasks"][0]
    assert task["title"] == "Test Task"
    assert task["status"] == "created"
    assert "src/app.py" in task.get("code_paths", [])


def test_export_includes_issues(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    epic = data["projects"][0]["epics"][0]
    assert len(epic["issues"]) == 1
    issue = epic["issues"][0]
    assert issue["title"] == "Test Issue"
    assert issue["severity"] == "high"


def test_export_includes_milestones(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    epic = data["projects"][0]["epics"][0]
    assert len(epic["milestones"]) == 1
    ms = epic["milestones"][0]
    assert ms["title"] == "Alpha"
    assert ms["date"] == "2026-07-15"


def test_export_includes_inbox(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    epic = data["projects"][0]["epics"][0]
    assert len(epic["inbox"]) == 1
    item = epic["inbox"][0]
    assert item["title"] == "Test Inbox"


def test_export_empty_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("developers: []\n", encoding="utf-8")
    data = export_repo(tmp_path)
    assert data["projects"] == []
    assert data["roster"] == []


def test_format_export_is_valid_json(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    data = export_repo(repo)
    rendered = format_export(data)
    parsed = json.loads(rendered)
    assert "projects" in parsed
    assert "roster" in parsed


def test_export_cli(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["export"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["projects"][0]["slug"] == "demo"


def test_export_cli_to_file(tmp_path: Path):
    repo = _repo_with_data(tmp_path)
    result = CliRunner().invoke(cli, ["export", "-o", "export.json"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "export.json" in result.output
    output_path = repo / "export.json"
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert data["projects"][0]["slug"] == "demo"
