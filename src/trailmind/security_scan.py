from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanFinding:
    path: Path
    message: str


_SKIPPED_DIR_NAMES = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}
_SKIPPED_FILE_NAMES = {".coverage", ".DS_Store", "coverage.xml"}
_SKIPPED_FILE_SUFFIXES = {".cache", ".log", ".pyc", ".pyo", ".tmp"}
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
_TOKEN_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd|private[_-]?key)"
        r"\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}['\"]?",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
)
_BLOCKED_TERM_PARTS = (
    ("team", "work"),
    ("byte", "dance"),
    ("cheng", "ming"),
)
_BLOCKED_TERM_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape("".join(parts)) for parts in _BLOCKED_TERM_PARTS)
    + r")\b",
    re.IGNORECASE,
)


def scan_paths(paths: list[Path]) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    for path in paths:
        for file_path in _iter_files(path):
            findings.extend(_scan_file(file_path))
    return findings


def _iter_files(path: Path):
    if path.is_dir():
        if _skip_dir(path):
            return
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(dirname for dirname in dirs if not _skip_dir(Path(root) / dirname))
            for filename in sorted(files):
                file_path = Path(root) / filename
                if not _skip_file(file_path):
                    yield file_path
    elif path.is_file() and not _skip_file(path):
        yield path


def _scan_file(path: Path) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    if path.name == ".env" or path.name.startswith(".env."):
        findings.append(ScanFinding(path, "sensitive environment file"))

    try:
        data = path.read_bytes()
    except OSError:
        return findings
    if b"\x00" in data:
        return findings
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return findings

    findings.extend(_scan_text(path, text))
    return findings


def _scan_text(path: Path, text: str) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    for match in _EMAIL_RE.finditer(text):
        if match.group(1).lower() != "example.com":
            findings.append(ScanFinding(path, "non-example.com email address"))
            break

    if any(pattern.search(text) for pattern in _TOKEN_PATTERNS):
        findings.append(ScanFinding(path, "token-like secret"))

    if _BLOCKED_TERM_RE.search(text):
        findings.append(ScanFinding(path, "blocked private term"))

    return findings


def _skip_dir(path: Path) -> bool:
    name = path.name
    return name in _SKIPPED_DIR_NAMES or name.endswith(".egg-info")


def _skip_file(path: Path) -> bool:
    return path.name in _SKIPPED_FILE_NAMES or path.suffix in _SKIPPED_FILE_SUFFIXES
