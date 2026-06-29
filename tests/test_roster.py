from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.roster import Roster, developer_uid


def test_developer_uid_is_six_digits():
    uid = developer_uid("alice@example.com")
    assert uid.isdigit()
    assert len(uid) == 6


def test_roster_add_and_lookup(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    roster = Roster.load(path)
    roster.add(email="alice@example.com", shortname="alice", name="Alice", uid="123456")
    roster.save()

    loaded = Roster.load(path)
    assert loaded.require_shortname("alice@example.com") == "alice"
    assert loaded.require_uid("alice@example.com") == "123456"


def test_roster_rejects_duplicate_email(tmp_path: Path):
    roster = Roster.load(tmp_path / "roster.yaml")
    roster.add(email="alice@example.com", shortname="alice", name="Alice", uid="123456")
    with pytest.raises(ValueError, match="already registered"):
        roster.add(email="alice@example.com", shortname="alice2", name="Alice 2", uid="654321")


def test_roster_cli_add_and_list(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    result = CliRunner().invoke(
        cli,
        ["roster", "add", "--email", "alice@example.com", "--shortname", "alice", "--name", "Alice", "--uid", "123456"],
        catch_exceptions=False,
        obj={"cwd": tmp_path},
    )
    assert result.exit_code == 0
    assert "Added alice@example.com as alice" in result.output

    list_result = CliRunner().invoke(cli, ["roster", "list"], catch_exceptions=False, obj={"cwd": tmp_path})
    assert list_result.exit_code == 0
    assert "alice@example.com" in list_result.output


def test_roster_cli_duplicate_email_is_user_facing(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    args = [
        "roster",
        "add",
        "--email",
        "alice@example.com",
        "--shortname",
        "alice",
        "--name",
        "Alice",
        "--uid",
        "123456",
    ]
    result = runner.invoke(cli, args, catch_exceptions=False, obj={"cwd": tmp_path})
    assert result.exit_code == 0

    duplicate_result = runner.invoke(cli, args, catch_exceptions=False, obj={"cwd": tmp_path})
    assert duplicate_result.exit_code == 1
    assert "error: alice@example.com is already registered" in duplicate_result.output
    assert "Traceback" not in duplicate_result.output
