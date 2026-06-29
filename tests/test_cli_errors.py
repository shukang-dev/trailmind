import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli

ERROR_MESSAGE = "error: not inside a Trailmind managed repository"


def test_cli_version_smoke():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "trailmind, version 0.1.0" in result.output


def test_cli_errors_do_not_show_traceback():
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_cli_errors_use_stderr():
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == ERROR_MESSAGE
    assert "Traceback" not in result.stderr


def test_module_entrypoint_errors_use_stderr():
    src_path = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_path)

    result = subprocess.run(
        [sys.executable, "-m", "trailmind", "status"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == ERROR_MESSAGE
    assert "Traceback" not in result.stderr
