from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from trailmind.entity_io import write_entity
from trailmind.errors import TrailmindError
from trailmind.log import action_activity_entry, append_activity_entry, read_entity_user_facing
from trailmind.resolver import resolve_entity
from trailmind.task_rules import (
    dependency_blockers,
    missing_deliverables,
    resolve_linked_issue,
    resolve_linked_task,
    soft_dependency_warnings,
    string_list_field,
)
from trailmind.task_status import is_terminal_task_status, normalize_task_status


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class PickupPack:
    kind: str
    generated_at: str
    item: dict[str, Any]
    dependencies: dict[str, Any] = field(default_factory=dict)
    linked_items: dict[str, Any] = field(default_factory=dict)
    deliverables: dict[str, Any] = field(default_factory=dict)
    activity: list[str] = field(default_factory=list)
    excerpts: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_base_pickup_pack(*, kind: str, repo_path: str) -> PickupPack:
    return PickupPack(
        kind=kind,
        generated_at=date.today().isoformat(),
        item={"path": repo_path},
    )


def pickup_pack_to_dict(pack: PickupPack) -> dict[str, Any]:
    return {
        "kind": pack.kind,
        "generated_at": pack.generated_at,
        "item": pack.item,
        "dependencies": pack.dependencies,
        "linked_items": pack.linked_items,
        "deliverables": pack.deliverables,
        "activity": pack.activity,
        "excerpts": pack.excerpts,
        "next_actions": pack.next_actions,
        "warnings": pack.warnings,
    }


def extract_markdown_section(body: str, heading: str) -> str | None:
    wanted = heading.strip().casefold()
    lines = body.splitlines()
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line.strip())
        if not match:
            continue
        if start is None and match.group(1).strip().casefold() == wanted:
            start = index + 1
            continue
        if start is not None:
            end = index
            break
    if start is None:
        return None
    text = "\n".join(lines[start:end]).strip()
    return text or None


def extract_activity_entries(body: str, *, limit: int) -> list[str]:
    if limit < 1:
        raise TrailmindError("activity limit must be at least 1")
    section = extract_markdown_section(body, "Activity Log")
    if not section:
        return []
    entries = [line.strip() for line in section.splitlines() if line.strip().startswith("- ")]
    return entries[-limit:]


def _safe_relative_path(raw: str) -> Path:
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        not raw.strip()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        raise TrailmindError(f"referenced path escapes repository: {raw}")
    return Path(*posix_path.parts)


def excerpt_file(repo_root: Path, raw_path: str, *, max_lines: int) -> dict[str, Any]:
    if max_lines < 1:
        raise TrailmindError("max lines must be at least 1")
    relative = _safe_relative_path(raw_path)
    display_path = relative.as_posix()
    path = repo_root / relative
    try:
        path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TrailmindError(f"referenced path escapes repository: {raw_path}") from exc
    if not path.exists():
        return {"path": display_path, "skipped": True, "skip_reason": "missing"}
    if path.is_dir():
        return {"path": display_path, "skipped": True, "skip_reason": "directory"}
    selected: list[str] = []
    total_lines = 0
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                total_lines += 1
                if len(selected) < max_lines:
                    selected.append(line.rstrip("\n"))
    except UnicodeDecodeError:
        return {"path": display_path, "skipped": True, "skip_reason": "non-utf-8"}
    except OSError as exc:
        return {"path": display_path, "skipped": True, "skip_reason": str(exc)}
    return {
        "path": display_path,
        "start_line": 1 if total_lines else 0,
        "end_line": len(selected),
        "total_lines": total_lines,
        "truncated": total_lines > max_lines,
        "content": "\n".join(selected),
        "skipped": False,
    }


def _relative_to_root(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _string_value(frontmatter: dict[str, Any], key: str, default: str = "") -> str:
    value = frontmatter.get(key)
    if value is None:
        return default
    return str(value)


def _task_next_actions(
    status: str,
    blockers: list[dict[str, Any]],
    missing: list[str],
    open_issues: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    if is_terminal_task_status(status):
        return [f"Task is terminal ({status}); do not pick it up for implementation unless reopening is intentional."]
    if blockers:
        actions.append("Hard dependencies are not terminal; do not start implementation yet.")
    if status == "blocked":
        actions.append("Task is blocked; resolve or update the blocker before implementation.")
    if missing:
        actions.append("Complete missing deliverables before closing the task.")
    if open_issues:
        actions.append("Review linked open issues before closing the task.")
    if not blockers and status in {"created", "ready"}:
        actions.append("Task is ready to start.")
    if status == "in_progress":
        actions.append("Continue from recent activity and verify current worktree state.")
    return actions


def _linked_task_summaries(repo_root: Path, issue_path: Path, refs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    tasks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for ref in refs:
        task_ref = ref.strip()
        try:
            task_path = resolve_linked_task(repo_root, issue_path, task_ref)
            frontmatter, _body = read_entity_user_facing(task_path, label="task")
            status = normalize_task_status(frontmatter.get("status", "created"))
            code_paths = string_list_field(frontmatter, "code_paths", label="task")
        except TrailmindError as exc:
            warnings.append(f"linked task {task_ref}: {exc.format_message()}")
            continue
        tasks.append(
            {
                "ref": task_ref,
                "task_id": _string_value(frontmatter, "id", task_path.stem),
                "title": _string_value(frontmatter, "title", task_path.stem),
                "status": status,
                "terminal": is_terminal_task_status(status),
                "path": _relative_to_root(repo_root, task_path),
                "code_paths": code_paths,
            }
        )
    return tasks, warnings


def _issue_next_actions(status: str, linked_tasks: list[dict[str, Any]], carried_into: list[str]) -> list[str]:
    if status in {"done", "wontfix"}:
        return [f"Issue is terminal ({status}); only pick it up if reopening is intentional."]
    actions: list[str] = []
    if linked_tasks:
        open_tasks = [item for item in linked_tasks if not item["terminal"]]
        if open_tasks:
            actions.append("Inspect linked task state before closing the issue.")
    else:
        actions.append("Decide whether to link this issue to a task, carry it forward, or close it.")
    if carried_into:
        actions.append("Inspect carried-into epics before changing issue status.")
    return actions


def _task_ref_status_to_dict(item: Any, repo_root: Path) -> dict[str, Any]:
    return {
        "ref": item.ref,
        "task_id": item.task_id,
        "title": item.title,
        "status": item.status,
        "terminal": item.terminal,
        "missing": item.missing,
        "path": _relative_to_root(repo_root, item.path) if item.path else None,
    }


def _known_issue_summaries(repo_root: Path, task_path: Path, refs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    for ref in refs:
        issue_ref = ref.strip()
        try:
            issue_path = resolve_linked_issue(repo_root, task_path, issue_ref)
            frontmatter, _body = read_entity_user_facing(issue_path, label="issue")
        except TrailmindError as exc:
            warnings.append(f"linked issue {issue_ref}: {exc.format_message()}")
            continue
        issues.append(
            {
                "id": _string_value(frontmatter, "id", issue_path.stem),
                "title": _string_value(frontmatter, "title", issue_path.stem),
                "status": _string_value(frontmatter, "status", "open"),
                "path": _relative_to_root(repo_root, issue_path),
            }
        )
    return issues, warnings


def _skipped_excerpt_refs(references: list[str]) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    for ref in references:
        relative = _safe_relative_path(ref)
        skipped.append({"path": relative.as_posix(), "skipped": True, "skip_reason": "excluded"})
    return skipped


def _excerpt_warnings(excerpts: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for excerpt in excerpts:
        if excerpt.get("skipped") and excerpt.get("skip_reason") != "excluded":
            warnings.append(f"{excerpt['path']} excerpt skipped: {excerpt.get('skip_reason')}")
    return warnings


def _issue_linked_task_excerpts(
    repo_root: Path,
    references: list[str],
    *,
    max_lines: int,
    include_excerpts: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    excerpts: list[dict[str, Any]] = []
    warnings: list[str] = []
    for ref in references:
        try:
            if include_excerpts:
                excerpts.append(excerpt_file(repo_root, ref, max_lines=max_lines))
            else:
                relative = _safe_relative_path(ref)
                excerpts.append({"path": relative.as_posix(), "skipped": True, "skip_reason": "excluded"})
        except TrailmindError as exc:
            warnings.append(f"linked task excerpt {ref}: {exc.format_message()}")
    return excerpts, warnings


def build_task_pickup(
    repo_root: Path,
    *,
    task_ref: str,
    max_lines: int = 80,
    activity_limit: int = 10,
    include_excerpts: bool = True,
) -> PickupPack:
    if max_lines < 1:
        raise TrailmindError("max lines must be at least 1")
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    status = normalize_task_status(frontmatter.get("status", "created"))
    depends_on = string_list_field(frontmatter, "depends_on", label="task")
    soft_depends_on = string_list_field(frontmatter, "soft_depends_on", label="task")
    known_issues = string_list_field(frontmatter, "known_issues", label="task")
    deliverables = string_list_field(frontmatter, "deliverables", label="task")
    completed = string_list_field(frontmatter, "completed_deliverables", label="task")
    blockers = [_task_ref_status_to_dict(item, repo_root) for item in dependency_blockers(repo_root, frontmatter)]
    soft_warnings = [_task_ref_status_to_dict(item, repo_root) for item in soft_dependency_warnings(repo_root, frontmatter)]
    issue_summaries, issue_warnings = _known_issue_summaries(repo_root, task_path, known_issues)
    open_issues = [item for item in issue_summaries if item["status"] == "open"]
    missing = missing_deliverables(frontmatter)
    references = string_list_field(frontmatter, "code_paths", label="task")
    design_doc = frontmatter.get("design_doc")
    if isinstance(design_doc, str) and design_doc.strip():
        references.append(design_doc.strip())
    excerpts = (
        [excerpt_file(repo_root, ref, max_lines=max_lines) for ref in references]
        if include_excerpts
        else _skipped_excerpt_refs(references)
    )
    warnings = (
        issue_warnings
        + [f"{item['task_id']} soft dependency is {item['status']}" for item in soft_warnings]
        + _excerpt_warnings(excerpts)
    )
    item = {
        "id": _string_value(frontmatter, "id", task_path.stem),
        "title": _string_value(frontmatter, "title", task_path.stem),
        "status": status,
        "owner": _string_value(frontmatter, "owner"),
        "filer": _string_value(frontmatter, "filer"),
        "path": _relative_to_root(repo_root, task_path),
        "scope": extract_markdown_section(body, "Scope"),
        "acceptance": extract_markdown_section(body, "Acceptance"),
        "frontmatter": {
            "depends_on": depends_on,
            "soft_depends_on": soft_depends_on,
            "known_issues": known_issues,
            "deliverables": deliverables,
            "completed_deliverables": completed,
            "code_paths": string_list_field(frontmatter, "code_paths", label="task"),
            "design_doc": design_doc,
            "branches": frontmatter.get("branches") or {},
            "verify": frontmatter.get("verify") or {},
        },
    }
    return PickupPack(
        kind="task",
        generated_at=date.today().isoformat(),
        item=item,
        dependencies={"hard": blockers, "soft": soft_warnings},
        linked_items={"issues": issue_summaries},
        deliverables={"required": deliverables, "completed": completed, "missing": missing},
        activity=extract_activity_entries(body, limit=activity_limit),
        excerpts=excerpts,
        next_actions=_task_next_actions(status, blockers, missing, open_issues),
        warnings=warnings,
    )


def build_issue_pickup(
    repo_root: Path,
    *,
    issue_ref: str,
    max_lines: int = 80,
    activity_limit: int = 10,
    include_excerpts: bool = True,
) -> PickupPack:
    if max_lines < 1:
        raise TrailmindError("max lines must be at least 1")
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")
    status = _string_value(frontmatter, "status", "open")
    linked_refs = string_list_field(frontmatter, "linked_tasks", label="issue")
    carried_into = string_list_field(frontmatter, "carried_into", label="issue")
    linked_tasks, warnings = _linked_task_summaries(repo_root, issue_path, linked_refs)
    excerpt_refs: list[str] = []
    for task in linked_tasks:
        excerpt_refs.extend(str(item) for item in task.get("code_paths", []))
    excerpts, excerpt_warnings = _issue_linked_task_excerpts(
        repo_root,
        excerpt_refs,
        max_lines=max_lines,
        include_excerpts=include_excerpts,
    )
    item = {
        "id": _string_value(frontmatter, "id", issue_path.stem),
        "title": _string_value(frontmatter, "title", issue_path.stem),
        "status": status,
        "severity": _string_value(frontmatter, "severity"),
        "filer": _string_value(frontmatter, "filer"),
        "path": _relative_to_root(repo_root, issue_path),
        "description": extract_markdown_section(body, "Description"),
        "resolution": extract_markdown_section(body, "Resolution"),
        "frontmatter": {"linked_tasks": linked_refs, "carried_into": carried_into},
    }
    return PickupPack(
        kind="issue",
        generated_at=date.today().isoformat(),
        item=item,
        dependencies={},
        linked_items={"tasks": linked_tasks},
        deliverables={},
        activity=extract_activity_entries(body, limit=activity_limit),
        excerpts=excerpts,
        next_actions=_issue_next_actions(status, linked_tasks, carried_into),
        warnings=warnings + excerpt_warnings + _excerpt_warnings(excerpts),
    )


def log_task_pickup(repo_root: Path, *, task_ref: str, actor: str, output_format: str) -> Path:
    task_path = resolve_entity(repo_root, raw=task_ref, entity="T")
    frontmatter, body = read_entity_user_facing(task_path, label="task")
    body = append_activity_entry(
        body,
        action_activity_entry(
            action="Picked up for handoff",
            actor_label="actor",
            actor=actor,
            note=f"Output format: {output_format}.",
        ),
    )
    write_entity(task_path, frontmatter=frontmatter, body=body)
    return task_path


def log_issue_pickup(repo_root: Path, *, issue_ref: str, actor: str, output_format: str) -> Path:
    issue_path = resolve_entity(repo_root, raw=issue_ref, entity="I")
    frontmatter, body = read_entity_user_facing(issue_path, label="issue")
    body = append_activity_entry(
        body,
        action_activity_entry(
            action="Picked up for handoff",
            actor_label="actor",
            actor=actor,
            note=f"Output format: {output_format}.",
        ),
    )
    write_entity(issue_path, frontmatter=frontmatter, body=body)
    return issue_path


def _list_lines(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _json_lines(items: list[dict[str, Any]], *, label: str) -> list[str]:
    if not items:
        return ["- none"]
    lines: list[str] = []
    for item in items:
        title = item.get("title") or item.get("task_id") or item.get("id") or label
        status = item.get("status", "unknown")
        path = item.get("path")
        suffix = f" ({path})" if path else ""
        lines.append(f"- {title} [{status}]{suffix}")
    return lines


def _markdown_code_fence(content: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def format_pickup_markdown(pack: PickupPack) -> str:
    title = f"{pack.item.get('id', '')} {pack.item.get('title', '')}".strip()
    heading_kind = "Task" if pack.kind == "task" else "Issue"
    lines = [f"# {heading_kind} Pickup: {title}", ""]
    lines.extend(["## Summary", f"- Path: {pack.item.get('path', '')}", f"- Status: {pack.item.get('status', '')}", ""])
    lines.extend(["## Current State"])
    scope = pack.item.get("scope") or pack.item.get("description")
    acceptance = pack.item.get("acceptance")
    resolution = pack.item.get("resolution")
    lines.append(scope if scope else "none")
    if acceptance:
        lines.extend(["", "Acceptance:", acceptance])
    if resolution:
        lines.extend(["", "Resolution:", resolution])
    lines.append("")
    if pack.kind == "task":
        lines.extend(["## Dependencies", "Hard:"])
        lines.extend(_json_lines(pack.dependencies.get("hard", []), label="dependency"))
        lines.append("")
        lines.append("Soft:")
        lines.extend(_json_lines(pack.dependencies.get("soft", []), label="dependency"))
        lines.append("")
        lines.extend(["## Deliverables"])
        lines.extend(_list_lines(pack.deliverables.get("missing", [])))
        lines.append("")
        lines.extend(["## Linked Issues"])
        lines.extend(_json_lines(pack.linked_items.get("issues", []), label="issue"))
        lines.append("")
    else:
        lines.extend(["## Linked Tasks"])
        lines.extend(_json_lines(pack.linked_items.get("tasks", []), label="task"))
        lines.append("")
    lines.extend(["## Recent Activity"])
    lines.extend(pack.activity if pack.activity else ["- none"])
    lines.append("")
    lines.extend(["## Relevant Files"])
    if pack.excerpts:
        for excerpt in pack.excerpts:
            lines.append(f"### {excerpt['path']}")
            if excerpt.get("skipped"):
                lines.append(f"- skipped: {excerpt.get('skip_reason')}")
            else:
                content = str(excerpt.get("content", ""))
                fence = _markdown_code_fence(content)
                lines.append(fence)
                lines.append(content)
                lines.append(fence)
    else:
        lines.append("none")
    lines.append("")
    lines.extend(["## Next Actions"])
    lines.extend(_list_lines(pack.next_actions))
    lines.append("")
    lines.extend(["## Warnings"])
    lines.extend(_list_lines(pack.warnings))
    return "\n".join(lines).rstrip() + "\n"
