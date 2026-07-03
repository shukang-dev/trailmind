from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_init_creates_roster_and_projects(tmp_path: Path):
    repo = _repo(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--no-ci", "--no-templates"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert (repo / "roster.yaml").exists()
    assert (repo / "projects").is_dir()
    assert "Initialized" in result.output or "already" in result.output or "skipping" in result.output


def test_init_creates_ci_workflow(tmp_path: Path):
    repo = _repo(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--no-templates"], obj={"cwd": repo})

    assert result.exit_code == 0
    ci = repo / ".github" / "workflows" / "ci.yml"
    assert ci.exists()
    content = ci.read_text()
    assert "python -m pytest" in content
    assert "trailmind scan" in content


def test_init_creates_templates(tmp_path: Path):
    repo = _repo(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--no-ci"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert (repo / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()
    assert (repo / ".github" / "ISSUE_TEMPLATE" / "bug_report.md").exists()
    assert (repo / ".github" / "ISSUE_TEMPLATE" / "feature_request.md").exists()


def test_init_is_idempotent(tmp_path: Path):
    repo = _repo(tmp_path)
    runner = CliRunner()

    first = runner.invoke(cli, ["init"], obj={"cwd": repo})
    assert first.exit_code == 0

    second = runner.invoke(cli, ["init"], obj={"cwd": repo})
    assert second.exit_code == 0
    assert "already exists" in second.output or "skipping" in second.output


def test_init_help_shows_options(tmp_path: Path):
    repo = _repo(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--help"], obj={"cwd": repo})
    assert result.exit_code == 0
    assert "--with-ci" in result.output
    assert "--with-templates" in result.output
