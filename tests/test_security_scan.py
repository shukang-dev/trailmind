from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.security_scan import ScanFinding, scan_paths


def test_scan_allows_public_fixtures(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "alice@example.com\nbob@example.com\ndemo_app\n",
        encoding="utf-8",
    )

    assert scan_paths([tmp_path]) == []


def test_scan_rejects_env_files(tmp_path: Path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("DEBUG=true\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings == [ScanFinding(env_file, "sensitive environment file")]


def test_scan_rejects_token_like_text(tmp_path: Path):
    secret_file = tmp_path / "settings.txt"
    secret_file.write_text('api_key = "' + ("a" * 32) + '"\n', encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings[0].path == secret_file
    assert "token-like secret" in findings[0].message


def test_scan_rejects_non_example_email(tmp_path: Path):
    contact_file = tmp_path / "contacts.txt"
    contact_file.write_text("owner: " + "alice@" + "company.test\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings[0].path == contact_file
    assert "non-example.com email" in findings[0].message


def test_scan_rejects_private_terms(tmp_path: Path):
    private_file = tmp_path / "notes.txt"
    private_file.write_text("vendor: " + "byte" + "dance\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings[0].path == private_file
    assert "blocked private term" in findings[0].message


def test_scan_skips_generated_directories(tmp_path: Path):
    for directory in [".git", ".venv", "__pycache__", ".pytest_cache", "dist", "build", "pkg.egg-info"]:
        path = tmp_path / directory
        path.mkdir()
        (path / "secret.txt").write_text('token = "' + ("b" * 32) + '"\n', encoding="utf-8")

    assert scan_paths([tmp_path]) == []


def test_scan_handles_binary_file(tmp_path: Path):
    binary_file = tmp_path / "image.bin"
    binary_file.write_bytes(b"\x80\x81\x00\xff")

    assert scan_paths([binary_file]) == []


def test_cli_scan_success_is_user_facing(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("alice@example.com\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["scan"], obj={"cwd": tmp_path})

    assert result.exit_code == 0
    assert result.stdout == "scan passed\n"
    assert result.stderr == ""


def test_cli_scan_failure_is_user_facing_without_traceback(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("DEBUG=true\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["scan"], obj={"cwd": tmp_path})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert ".env: sensitive environment file" in result.stderr
    assert "error: security scan found 1 finding" in result.stderr
    assert "Traceback" not in result.stderr
