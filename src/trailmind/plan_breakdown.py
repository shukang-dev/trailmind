from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.errors import TrailmindError
from trailmind.log import read_entity_user_facing
from trailmind.roster import Roster


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


@dataclass(frozen=True)
class BreakdownItem:
    source_task: int
    source_heading: str
    title: str
    action: str
    existing_path: str | None
    code_paths: list[str]
    deliverables: list[str]
    plan_task: PlanTask


@dataclass(frozen=True)
class BreakdownReport:
    plan_path: str
    epic_path: str
    write: bool
    force: bool
    tasks: list[BreakdownItem]
    created: list[str]
    skipped: list[str]


def build_breakdown_report(
    repo_root: Path,
    *,
    plan_ref: str,
    epic_ref: str,
    filer: str,
    owner: str,
    write: bool,
    force: bool,
) -> BreakdownReport:
    plan_path = _resolve_plan_path(repo_root, plan_ref)
    epic_path = _resolve_epic_path(repo_root, epic_ref)
    roster = Roster.load(repo_root / "roster.yaml")
    filer_shortname, filer_uid = _resolve_roster_developer(roster, filer)
    owner_shortname, _owner_uid = _resolve_roster_developer(roster, owner)
    _ = (filer_shortname, filer_uid, owner_shortname)
    plan_text = _read_plan_text(plan_path)
    plan_tasks = parse_plan_tasks(plan_text)
    existing = _existing_source_tasks(repo_root, epic_path)
    plan_display = _relative_to_root(repo_root, plan_path)
    epic_display = _relative_to_root(repo_root, epic_path)
    items: list[BreakdownItem] = []
    skipped: list[str] = []
    for plan_task in plan_tasks:
        existing_path = existing.get((plan_display, plan_task.source_task))
        action = "create"
        if existing_path and not force:
            action = "skip"
            skipped.append(existing_path)
        elif existing_path and force:
            action = "duplicate allowed by --force"
        items.append(
            BreakdownItem(
                source_task=plan_task.source_task,
                source_heading=plan_task.source_heading,
                title=plan_task.title,
                action=action,
                existing_path=existing_path,
                code_paths=derive_code_paths(plan_task),
                deliverables=derive_deliverables(plan_task),
                plan_task=plan_task,
            )
        )
    if write:
        raise TrailmindError("write mode unavailable in preview-only implementation")
    return BreakdownReport(
        plan_path=plan_display,
        epic_path=epic_display,
        write=write,
        force=force,
        tasks=items,
        created=[],
        skipped=skipped,
    )


def breakdown_report_to_dict(report: BreakdownReport) -> dict[str, Any]:
    return {
        "plan_path": report.plan_path,
        "epic_path": report.epic_path,
        "write": report.write,
        "force": report.force,
        "tasks": [
            {
                "source_task": item.source_task,
                "source_heading": item.source_heading,
                "title": item.title,
                "action": item.action,
                "existing_path": item.existing_path,
                "code_paths": item.code_paths,
                "deliverables": item.deliverables,
            }
            for item in report.tasks
        ],
        "created": report.created,
        "skipped": report.skipped,
    }


def format_breakdown_markdown(report: BreakdownReport) -> str:
    heading = "# Plan Breakdown Write" if report.write else "# Plan Breakdown Preview"
    lines = [
        heading,
        "",
        f"- Plan: {report.plan_path}",
        f"- Epic: {report.epic_path}",
        f"- Tasks parsed: {len(report.tasks)}",
        f"- Created: {len(report.created)}",
        f"- Skipped: {len(report.skipped)}",
        "",
        "## Tasks",
    ]
    if not report.tasks:
        lines.append("- none")
    for item in report.tasks:
        existing = f" existing={item.existing_path}" if item.existing_path else ""
        lines.append(f"- Task {item.source_task}: {item.title} [{item.action}]{existing}")
        lines.append(f"  - Source: {item.source_heading}")
        paths = ", ".join(item.code_paths) if item.code_paths else "none"
        deliverables = ", ".join(item.deliverables) if item.deliverables else "none"
        lines.append(f"  - Code paths: {paths}")
        lines.append(f"  - Deliverables: {deliverables}")
    if report.created:
        lines.extend(["", "## Created Paths"])
        lines.extend(f"- {path}" for path in report.created)
    if report.skipped:
        lines.extend(["", "## Skipped Paths"])
        lines.extend(f"- {path}" for path in report.skipped)
    return "\n".join(lines).rstrip() + "\n"


def _resolve_plan_path(repo_root: Path, raw: str) -> Path:
    relative = _safe_relative_path(raw)
    path = repo_root / relative
    try:
        path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"plan path {raw!r} not found") from exc
    if path.suffix != ".md":
        raise TrailmindError("plan path must be a Markdown file")
    if not path.is_file():
        raise TrailmindError(f"plan path {raw!r} not found")
    return path


def _resolve_epic_path(repo_root: Path, raw: str) -> Path:
    relative = _safe_relative_path(raw)
    path = repo_root / relative
    try:
        path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"epic {raw} does not exist") from exc
    if not (path / "EPIC.md").is_file():
        raise TrailmindError(f"epic {raw} does not exist")
    return path


def _safe_relative_path(raw: str) -> Path:
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw.strip()
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or windows.root
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise TrailmindError(f"path escapes repository: {raw}")
    return Path(*posix.parts)


def _read_plan_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TrailmindError(f"could not read plan file {path}: file is not UTF-8") from exc
    except OSError as exc:
        raise TrailmindError(f"could not read plan file {path}: {exc}") from exc


def _resolve_roster_developer(roster: Roster, raw: str) -> tuple[str, str]:
    normalized = raw.strip().lower()
    for developer in roster.developers:
        if developer.email == normalized or developer.shortname.lower() == normalized:
            return developer.shortname, developer.uid
    raise TrailmindError(f"{normalized} is not registered in roster.yaml")


def _existing_source_tasks(repo_root: Path, epic_path: Path) -> dict[tuple[str, int], str]:
    tasks_path = epic_path / "tasks"
    if tasks_path.exists() and not tasks_path.is_dir():
        raise TrailmindError(f"tasks path {tasks_path} is not a directory")
    existing: dict[tuple[str, int], str] = {}
    if not tasks_path.exists():
        return existing
    for path in sorted(tasks_path.glob("T-*.md")):
        try:
            frontmatter, _body = read_entity_user_facing(path, label="task")
        except TrailmindError:
            continue
        source_plan = frontmatter.get("source_plan")
        source_task = frontmatter.get("source_task")
        if isinstance(source_task, str) and source_task.isdigit():
            source_task = int(source_task)
        if isinstance(source_plan, str) and isinstance(source_task, int):
            existing[(source_plan, source_task)] = _relative_to_root(repo_root, path)
    return existing


def _relative_to_root(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
