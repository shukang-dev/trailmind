from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

from trailmind.errors import TrailmindError


TASK_HEADING_RE = re.compile(r"^###[ \t]+Task[ \t]+(\d+):[ \t]+([^ \t].*?)[ \t]*$")
TASK_MARKER_RE = re.compile(r"^###[ \t]+Task\b")
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
FILE_ENTRY_RE = re.compile(r"^-\s+([^:]+):\s+`?([^`\n]+?)`?\s*$")
STEP_RE = re.compile(r"^-\s+\[\s*\]\s+\*\*(Step\s+\d+:.+?)\*\*\s*$")
COMMIT_RE = re.compile(r"git\s+commit\s+-m\s+([\"'])(.+?)\1")


@dataclass(frozen=True)
class PlanTask:
    source_task: int
    source_heading: str
    title: str
    source_context: str
    file_entries: list[tuple[str, str]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    commit_message: str | None = None


@dataclass(frozen=True)
class _TaskHeading:
    source_task: int
    title: str
    start: int
    end: int


def parse_plan_tasks(text: str) -> list[PlanTask]:
    headings = _find_task_headings(text)
    if not headings:
        raise TrailmindError("plan contains no supported task sections")

    tasks: list[PlanTask] = []
    for index, heading in enumerate(headings):
        section_start = heading.end
        section_end = headings[index + 1].start if index + 1 < len(headings) else len(text)
        section = text[section_start:section_end].strip()
        source_heading = f"Task {heading.source_task}: {heading.title}"
        tasks.append(
            PlanTask(
                source_task=heading.source_task,
                source_heading=source_heading,
                title=heading.title,
                source_context=section,
                file_entries=_extract_file_entries(section),
                steps=_extract_steps(section),
                verification_commands=_extract_verification_commands(section),
                commit_message=_extract_commit_message(section),
            )
        )
    return tasks


def _find_task_headings(text: str) -> list[_TaskHeading]:
    headings: list[_TaskHeading] = []
    offset = 0
    active_fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        line_text = line.rstrip("\r\n")
        fence = _fence_marker(line_text)
        if active_fence:
            if fence and fence[0] == active_fence[0] and fence[1] >= active_fence[1]:
                active_fence = None
            offset += len(line)
            continue
        if fence:
            active_fence = fence
            offset += len(line)
            continue

        match = TASK_HEADING_RE.match(line_text)
        if match:
            headings.append(
                _TaskHeading(
                    source_task=int(match.group(1)),
                    title=match.group(2).strip(),
                    start=offset,
                    end=offset + len(line),
                )
            )
        elif TASK_MARKER_RE.match(line_text):
            raise TrailmindError("malformed task heading; expected '### Task N: Title'")
        offset += len(line)
    return headings


def _fence_marker(line: str) -> tuple[str, int] | None:
    match = FENCE_RE.match(line)
    if not match:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


def _extract_file_entries(section: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    in_files = False
    for line in section.splitlines():
        stripped = line.strip()
        if stripped == "**Files:**":
            in_files = True
            continue
        if in_files and stripped.startswith("**") and stripped.endswith("**"):
            break
        if in_files and stripped.startswith("###"):
            break
        if in_files and stripped.startswith("- ["):
            break
        if not in_files or not stripped:
            continue
        match = FILE_ENTRY_RE.match(stripped)
        if match:
            entries.append((match.group(1).strip(), match.group(2).strip()))
    return entries


def _extract_steps(section: str) -> list[str]:
    steps: list[str] = []
    for line in section.splitlines():
        match = STEP_RE.match(line.strip())
        if match:
            steps.append(match.group(1).strip())
    return steps


def _extract_verification_commands(section: str) -> list[str]:
    commands: list[str] = []
    lines = section.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("Run:"):
            inline = line.removeprefix("Run:").strip()
            if inline and not inline.startswith("```"):
                commands.append(inline.strip("`"))
            else:
                cursor = index + 1
                while cursor < len(lines) and not lines[cursor].strip():
                    cursor += 1
                fence = _fence_marker(lines[cursor]) if cursor < len(lines) else None
                if fence:
                    cursor += 1
                    while cursor < len(lines):
                        command = lines[cursor].strip()
                        closing_fence = _fence_marker(lines[cursor])
                        if closing_fence and closing_fence[0] == fence[0] and closing_fence[1] >= fence[1]:
                            break
                        if command:
                            commands.append(command)
                        cursor += 1
                    index = cursor
        index += 1
    return commands


def _extract_commit_message(section: str) -> str | None:
    match = COMMIT_RE.search(section)
    if not match:
        return None
    return match.group(2).strip()


def derive_code_paths(task: PlanTask) -> list[str]:
    paths: list[str] = []
    for _label, raw in task.file_entries:
        candidate = _strip_line_suffix(raw)
        if not _is_supported_code_path(candidate):
            continue
        if candidate not in paths:
            paths.append(candidate)
    return paths


def derive_deliverables(task: PlanTask) -> list[str]:
    deliverables = ["tests pass", "plan task implemented"]
    text = f"{task.title}\n{task.source_context}".casefold()
    if any(path.startswith("docs/") for path in derive_code_paths(task)) or "documentation" in text or "docs" in text:
        deliverables.append("docs updated")
    return deliverables


def _strip_line_suffix(raw: str) -> str:
    value = raw.strip()
    if ":" in value:
        head, tail = value.rsplit(":", 1)
        if tail.replace("-", "").isdigit():
            value = head
    return value


def _is_supported_code_path(raw: str) -> bool:
    if not raw or raw.startswith("-"):
        return False
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        return False
    if ".." in posix.parts or ".." in windows.parts:
        return False
    return raw.startswith(("src/", "tests/", "docs/")) and "." in posix.name
