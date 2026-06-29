from __future__ import annotations

import subprocess
from pathlib import Path

from trailmind.errors import TrailmindError


def stage_paths(repo_root: Path, paths: list[Path]) -> None:
    """Stage exactly the provided repository paths."""
    relative_paths = _relative_paths(repo_root, paths)
    if not relative_paths:
        return
    _run_git(repo_root, ["add", "--", *relative_paths], "add")


def commit_paths(repo_root: Path, paths: list[Path], message: str) -> None:
    """Stage and commit exactly the provided repository paths."""
    relative_paths = _relative_paths(repo_root, paths)
    if not relative_paths:
        return
    stage_paths(repo_root, paths)
    _run_git(repo_root, ["commit", "-m", message, "--", *relative_paths], "commit")


def _relative_paths(repo_root: Path, paths: list[Path]) -> list[str]:
    root = repo_root.resolve(strict=False)
    relative_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise TrailmindError(f"path {path} is outside repository {root}") from exc
        relative_posix = relative.as_posix()
        if relative_posix in {"", "."}:
            raise TrailmindError("refusing to stage repository root")
        if relative_posix not in seen:
            relative_paths.append(relative_posix)
            seen.add(relative_posix)
    return relative_paths


def _run_git(repo_root: Path, args: list[str], action: str) -> None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise TrailmindError(f"could not run git {action}: {exc}") from exc
    if result.returncode != 0:
        raise TrailmindError(_git_failure_message(action, result))


def _git_failure_message(action: str, result: subprocess.CompletedProcess[str]) -> str:
    details = [f"git {action} failed"]
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    if stderr:
        details.append(f"stderr: {stderr}")
    if stdout:
        details.append(f"stdout: {stdout}")
    return "\n".join(details)
