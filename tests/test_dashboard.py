from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo_with_dashboard_data(tmp_path: Path) -> Path:
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
            "--owners",
            "alice",
            "--tags",
            "demo",
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
            "--start",
            "2026-06-29",
            "--target",
            "2026-07-15",
        ],
        obj={"cwd": tmp_path},
    )
    assert epic_result.exit_code == 0
    task_result = runner.invoke(
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
        obj={"cwd": tmp_path},
    )
    assert task_result.exit_code == 0
    issue_result = runner.invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--title",
            "Parser drops flags",
            "--description",
            "Flags disappear during parsing.",
            "--severity",
            "high",
        ],
        obj={"cwd": tmp_path},
    )
    assert issue_result.exit_code == 0
    milestone_result = runner.invoke(
        cli,
        [
            "milestone",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--title",
            "Parser Alpha",
            "--date",
            "2026-07-15",
        ],
        obj={"cwd": tmp_path},
    )
    assert milestone_result.exit_code == 0
    return tmp_path


def test_status_overview_project_and_epic_render_static_dashboards(tmp_path: Path):
    repo = _repo_with_dashboard_data(tmp_path)
    runner = CliRunner()

    overview_result = runner.invoke(cli, ["status", "--overview"], obj={"cwd": repo})
    assert overview_result.exit_code == 0
    overview_path = repo / "overview.html"
    assert overview_path.exists()
    assert "overview.html" in overview_result.output
    assert "Demo App" in overview_path.read_text(encoding="utf-8")

    project_result = runner.invoke(cli, ["status", "--project", "demo_app"], obj={"cwd": repo})
    assert project_result.exit_code == 0
    project_path = repo / "projects" / "demo_app" / "dashboard.html"
    assert project_path.exists()
    project_html = project_path.read_text(encoding="utf-8")
    assert "MVP" in project_html
    assert "First usable release" in project_html

    epic_result = runner.invoke(cli, ["status", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})
    assert epic_result.exit_code == 0
    epic_path = repo / "projects" / "demo_app" / "mvp" / "dashboard.html"
    assert epic_path.exists()
    epic_html = epic_path.read_text(encoding="utf-8")
    assert "Build parser" in epic_html
    assert "Parser drops flags" in epic_html
    assert "Parser Alpha" in epic_html


def test_status_without_flags_is_scope_aware_for_project_and_epic(tmp_path: Path):
    repo = _repo_with_dashboard_data(tmp_path)
    runner = CliRunner()

    project_dir = repo / "projects" / "demo_app"
    project_result = runner.invoke(cli, ["status"], obj={"cwd": project_dir})
    assert project_result.exit_code == 0
    assert (project_dir / "dashboard.html").exists()
    assert "projects/demo_app/dashboard.html" in project_result.output

    epic_dir = repo / "projects" / "demo_app" / "mvp"
    epic_result = runner.invoke(cli, ["status"], obj={"cwd": epic_dir})
    assert epic_result.exit_code == 0
    assert (epic_dir / "dashboard.html").exists()
    assert "projects/demo_app/mvp/dashboard.html" in epic_result.output


def test_status_without_flags_defaults_to_overview(tmp_path: Path):
    repo = _repo_with_dashboard_data(tmp_path)

    result = CliRunner().invoke(cli, ["status"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert (repo / "overview.html").exists()
    assert "overview.html" in result.output


def test_status_missing_project_or_epic_is_user_facing(tmp_path: Path):
    repo = _repo_with_dashboard_data(tmp_path)
    runner = CliRunner()

    project_result = runner.invoke(cli, ["status", "--project", "missing"], obj={"cwd": repo})
    assert project_result.exit_code == 1
    assert "error:" in project_result.output
    assert "project missing does not exist" in project_result.output
    assert "Traceback" not in project_result.output

    epic_result = runner.invoke(cli, ["status", "--epic", "projects/demo_app/missing"], obj={"cwd": repo})
    assert epic_result.exit_code == 1
    assert "error:" in epic_result.output
    assert "epic projects/demo_app/missing does not exist" in epic_result.output
    assert "Traceback" not in epic_result.output


def test_status_malformed_task_or_issue_frontmatter_is_user_facing(tmp_path: Path):
    repo = _repo_with_dashboard_data(tmp_path)
    task_path = repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-999-bad.md"
    task_path.write_text("---\n: bad\n---\n# Bad\n", encoding="utf-8")

    task_result = CliRunner().invoke(cli, ["status", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})
    assert task_result.exit_code == 1
    assert "error:" in task_result.output
    assert "malformed YAML frontmatter" in task_result.output
    assert "Traceback" not in task_result.output

    task_path.unlink()
    issue_path = repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-999-bad.md"
    issue_path.write_text("plain markdown\n", encoding="utf-8")

    issue_result = CliRunner().invoke(cli, ["status", "--epic", "projects/demo_app/mvp"], obj={"cwd": repo})
    assert issue_result.exit_code == 1
    assert "error:" in issue_result.output
    assert "missing YAML frontmatter" in issue_result.output
    assert "Traceback" not in issue_result.output


def test_serve_command_invokes_static_server(monkeypatch, tmp_path: Path):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_serve(repo_root: Path, *, host: str, port: int) -> None:
        calls.append((repo_root, host, port))

    monkeypatch.setattr("trailmind.cli.serve_repo", fake_serve)

    result = CliRunner().invoke(
        cli,
        ["serve", "--host", "127.0.0.1", "--port", "8888"],
        obj={"cwd": tmp_path},
    )

    assert result.exit_code == 0
    assert calls == [(tmp_path, "127.0.0.1", 8888)]
