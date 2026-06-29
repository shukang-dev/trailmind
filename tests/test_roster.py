from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.errors import TrailmindError
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


def test_roster_add_rejects_empty_supplied_uid(tmp_path: Path):
    roster = Roster.load(tmp_path / "roster.yaml")
    with pytest.raises(ValueError, match="uid must be exactly six digits"):
        roster.add(email="alice@example.com", shortname="alice", name="Alice", uid="")


def test_roster_load_rejects_invalid_yaml(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("developers: [\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="invalid roster.yaml"):
        Roster.load(path)


def test_roster_load_rejects_non_mapping_top_level(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("- nope\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="invalid roster.yaml"):
        Roster.load(path)


def test_roster_load_rejects_falsey_non_mapping_top_level(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="invalid roster.yaml"):
        Roster.load(path)


def test_roster_load_rejects_bad_developer_shape(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("developers:\n- email: alice@example.com\n  shortname: alice\n  name: Alice\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="invalid roster.yaml"):
        Roster.load(path)


def test_roster_load_rejects_invalid_persisted_uid(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("developers:\n- email: alice@example.com\n  shortname: alice\n  uid: abc\n  name: Alice\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="uid must be exactly six digits"):
        Roster.load(path)


def test_roster_load_rejects_ambiguous_integer_uid(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text("developers:\n- email: alice@example.com\n  shortname: alice\n  uid: 5349\n  name: Alice\n", encoding="utf-8")
    with pytest.raises(TrailmindError, match="uid must be exactly six digits"):
        Roster.load(path)


def test_roster_load_accepts_canonical_integer_uid(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text(
        "developers:\n- email: alice@example.com\n  shortname: alice\n  uid: 123456\n  name: Alice\n",
        encoding="utf-8",
    )

    roster = Roster.load(path)

    assert roster.require_uid("alice@example.com") == "123456"


def test_roster_load_rejects_duplicate_persisted_email(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: ALICE@example.com\n  shortname: alice2\n  uid: '654321'\n  name: Alice 2\n",
        encoding="utf-8",
    )
    with pytest.raises(TrailmindError, match="already registered"):
        Roster.load(path)


def test_roster_load_rejects_duplicate_persisted_shortname(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: alice2@example.com\n  shortname: alice\n  uid: '654321'\n  name: Alice 2\n",
        encoding="utf-8",
    )
    with pytest.raises(TrailmindError, match="shortname alice is already registered"):
        Roster.load(path)


def test_roster_load_rejects_duplicate_persisted_uid(tmp_path: Path):
    path = tmp_path / "roster.yaml"
    path.write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: alice2@example.com\n  shortname: alice2\n  uid: '123456'\n  name: Alice 2\n",
        encoding="utf-8",
    )
    with pytest.raises(TrailmindError, match="uid 123456 is already registered"):
        Roster.load(path)


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


def test_roster_cli_rejects_empty_supplied_uid(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    result = CliRunner().invoke(
        cli,
        ["roster", "add", "--email", "alice@example.com", "--shortname", "alice", "--name", "Alice", "--uid", ""],
        obj={"cwd": tmp_path},
    )
    assert result.exit_code == 1
    assert "error: uid must be exactly six digits" in result.output
    assert "Traceback" not in result.output


def test_roster_cli_bad_file_is_user_facing(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("developers: [\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["roster", "list"], obj={"cwd": tmp_path})
    assert result.exit_code == 1
    assert "error: invalid roster.yaml" in result.output
    assert "Traceback" not in result.output


def test_roster_cli_add_bad_file_is_user_facing(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text("developers: [\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        ["roster", "add", "--email", "alice@example.com", "--shortname", "alice", "--name", "Alice"],
        obj={"cwd": tmp_path},
    )
    assert result.exit_code == 1
    assert "error: invalid roster.yaml" in result.output
    assert "Traceback" not in result.output
