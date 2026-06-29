from click.testing import CliRunner

from trailmind.cli import cli


def test_cli_version_smoke():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "trailmind, version 0.1.0" in result.output


def test_cli_errors_do_not_show_traceback():
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
