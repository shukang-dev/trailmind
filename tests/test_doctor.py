import json
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.doctor import format_doctor_report, run_doctor


def _repo_with_project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing", "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com", "--owner", "alice@example.com", "--title", "Test Task"], obj={"cwd": tmp_path})
    return tmp_path


def test_doctor_clean_repo_has_no_errors(tmp_path: Path):
    repo = _repo_with_project(tmp_path)
    findings = run_doctor(repo)
    errors = [f for f in findings if f.severity == "error"]
    assert len(errors) == 0


def test_doctor_missing_roster(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    findings = run_doctor(tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert any("roster.yaml" in f.message for f in errors)


def test_doctor_invalid_yaml_roster(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    findings = run_doctor(tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert any("not valid YAML" in f.message for f in errors)


def test_doctor_missing_git(tmp_path: Path):
    (tmp_path / "roster.yaml").write_text("developers: []\n", encoding="utf-8")
    findings = run_doctor(tmp_path)
    warnings = [f for f in findings if f.severity == "warning"]
    assert any(".git" in f.message for f in warnings)


def test_doctor_empty_repo_shows_info(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("developers: []\n", encoding="utf-8")
    findings = run_doctor(tmp_path)
    infos = [f for f in findings if f.severity == "info"]
    assert any("No projects" in f.message for f in infos)


def test_doctor_cli_clean(tmp_path: Path):
    repo = _repo_with_project(tmp_path)
    result = CliRunner().invoke(cli, ["doctor"], obj={"cwd": repo})
    assert result.exit_code == 0


def test_doctor_cli_missing_roster(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    result = CliRunner().invoke(cli, ["doctor"], obj={"cwd": tmp_path})
    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_doctor_cli_json(tmp_path: Path):
    repo = _repo_with_project(tmp_path)
    result = CliRunner().invoke(cli, ["doctor", "--json"], obj={"cwd": repo})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_format_doctor_report_clean():
    assert "All checks passed" in format_doctor_report([])


def test_format_doctor_report_with_findings():
    from trailmind.doctor import DoctorFinding
    findings = [
        DoctorFinding(severity="error", message="Bad thing", path="file.md"),
        DoctorFinding(severity="warning", message="Careful", path=None),
    ]
    rendered = format_doctor_report(findings)
    assert "ERROR" in rendered
    assert "WARN" in rendered
    assert "Bad thing" in rendered
    assert "Careful" in rendered
