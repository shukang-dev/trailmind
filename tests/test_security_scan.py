from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.security_scan import ScanFinding, scan_paths


def test_scan_allows_public_fixtures(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "user@example.com\nreviewer@example.com\ndemo_app\n",
        encoding="utf-8",
    )

    assert scan_paths([tmp_path]) == []


@pytest.mark.parametrize("filename", [".env", ".env.local", ".env.log", ".env.tmp"])
def test_scan_rejects_env_files(tmp_path: Path, filename: str):
    env_file = tmp_path / filename
    env_file.write_text("DEBUG=true\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings == [ScanFinding(env_file, "sensitive environment file")]


def test_scan_rejects_token_like_text(tmp_path: Path):
    secret_file = tmp_path / "settings.txt"
    secret_file.write_text('api_key = "' + ("a" * 32) + '"\n', encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings == [ScanFinding(secret_file, "token-like secret")]


def test_scan_rejects_non_example_email(tmp_path: Path):
    contact_file = tmp_path / "contacts.txt"
    contact_file.write_text("owner: " + "user@" + "sample.invalid\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings == [ScanFinding(contact_file, "non-example.com email address")]


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("marker.txt", "marker: " + "internal" + "-only\n"),
        ("system.txt", "marker: " + "proprietary" + "-system\n"),
        ("fixture.txt", "fixture: " + "private" + "-fixture\n"),
        ("internal-path.txt", "path: " + "/internal" + "/service/config\n"),
        ("private-path.txt", "path: " + "/private" + "/fixture/config\n"),
    ],
)
def test_scan_rejects_private_release_markers(tmp_path: Path, filename: str, content: str):
    private_file = tmp_path / filename
    private_file.write_text(content, encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert findings == [ScanFinding(private_file, "blocked private term")]


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
    (tmp_path / "README.md").write_text("user@example.com\n", encoding="utf-8")

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
