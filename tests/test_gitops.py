import subprocess
from pathlib import Path

import pytest

from trailmind.errors import TrailmindError
from trailmind.gitops import commit_paths, stage_paths


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init")


def _staged_paths(repo: Path) -> list[str]:
    result = _git(repo, "diff", "--cached", "--name-only")
    return [line for line in result.stdout.splitlines() if line]


def test_stage_paths_stages_only_touched_files(tmp_path: Path):
    _init_repo(tmp_path)
    touched = tmp_path / "touched.txt"
    untouched = tmp_path / "untouched.txt"
    touched.write_text("changed\n", encoding="utf-8")
    untouched.write_text("do not stage\n", encoding="utf-8")

    stage_paths(tmp_path, [touched])

    assert _staged_paths(tmp_path) == ["touched.txt"]


def test_stage_paths_empty_list_is_noop(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "untouched.txt").write_text("do not stage\n", encoding="utf-8")

    stage_paths(tmp_path, [])

    assert _staged_paths(tmp_path) == []


def test_stage_paths_rejects_outside_repo_and_does_not_stage_unrelated_file(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    unrelated = repo / "unrelated.txt"
    outside = tmp_path / "outside.txt"
    unrelated.write_text("keep unstaged\n", encoding="utf-8")
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(TrailmindError, match="outside repository"):
        stage_paths(repo, [outside])

    assert _staged_paths(repo) == []


def test_commit_paths_commits_only_requested_paths(tmp_path: Path):
    _init_repo(tmp_path)
    _git(tmp_path, "config", "user.email", "alice@example.com")
    _git(tmp_path, "config", "user.name", "Alice")
    requested = tmp_path / "requested.txt"
    unrelated = tmp_path / "unrelated.txt"
    requested.write_text("before\n", encoding="utf-8")
    unrelated.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "--", "requested.txt", "unrelated.txt")
    _git(tmp_path, "commit", "-m", "initial")
    requested.write_text("after\n", encoding="utf-8")
    unrelated.write_text("after\n", encoding="utf-8")
    _git(tmp_path, "add", "--", "unrelated.txt")

    commit_paths(tmp_path, [requested], "update requested")

    changed = _git(tmp_path, "show", "--name-only", "--format=", "HEAD").stdout.splitlines()
    assert changed == ["requested.txt"]
    assert _staged_paths(tmp_path) == ["unrelated.txt"]
