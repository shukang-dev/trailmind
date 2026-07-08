from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from trailmind.log import read_entity_user_facing
from trailmind.resolver import resolve_entity


def show_entity(repo_root: Path, entity_ref: str, entity_prefix: str) -> dict[str, Any]:
    """Show a single entity's details as a structured dict."""
    path = resolve_entity(repo_root, raw=entity_ref, entity=entity_prefix)
    frontmatter, body = read_entity_user_facing(path, label=entity_prefix.lower())
    result: dict[str, Any] = {
        "path": str(path.relative_to(repo_root)),
        "body": body.strip(),
    }
    for key, value in frontmatter.items():
        if value is not None:
            result[key] = value

    # Derive epic from path (projects/<project>/<epic>/...)
    rel = str(path.relative_to(repo_root))
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "projects":
        result["_epic"] = f"projects/{parts[1]}/{parts[2]}"
        result["_project"] = parts[1]
        result["_epic_slug"] = parts[2]

    # Count comments and activity entries from body
    result["_comment_count"] = body.count("**") // 2  # rough count
    result["_activity_count"] = len(re.findall(r"^\s*-\s+\d{4}-\d{2}-\d{2}:", body, re.MULTILINE))

    return result


def format_entity_show(data: dict[str, Any], *, entity_label: str) -> str:
    """Format entity details as a readable text report."""
    lines = []
    title = data.get("title", data.get("id", "Unknown"))
    lines.append(f"=== {entity_label}: {title} ===")
    lines.append("")

    # Key fields first
    key_fields = ["id", "slug", "status", "state", "priority", "severity",
                  "owner", "filer", "date", "due", "start", "target",
                  "created", "resolved", "scope", "project", "goal"]
    for field in key_fields:
        if field in data and data[field]:
            lines.append(f"  {field:12s}: {data[field]}")

    # Epic context (derived from path)
    if "_epic" in data:
        lines.append(f"  {'epic':12s}: {data['_epic']}")

    # Deliverable progress
    deliverables = data.get("deliverables") or []
    completed = data.get("completed_deliverables") or []
    if deliverables:
        total = len(deliverables)
        done = len(completed)
        pct = round(done / total * 100) if total > 0 else 0
        lines.append(f"  {'deliverables':12s}: {done}/{total} done ({pct}%)")
        for d in deliverables:
            status = "✓" if d in completed else "○"
            lines.append(f"    {status} {d}")

    # Dependencies
    hard_deps = data.get("depends_on") or []
    soft_deps = data.get("soft_depends_on") or []
    if hard_deps:
        lines.append(f"  {'blocked by':12s}: {', '.join(hard_deps)}")
    if soft_deps:
        lines.append(f"  {'soft deps':12s}: {', '.join(soft_deps)}")

    # Known issues
    known_issues = data.get("known_issues") or []
    if known_issues:
        lines.append(f"  {'known issues':12s}: {', '.join(known_issues)}")

    # Linked tasks (for issues)
    linked_tasks = data.get("linked_tasks") or []
    if linked_tasks:
        lines.append(f"  {'linked tasks':12s}: {', '.join(linked_tasks)}")

    # List fields (code_paths, tags, etc.)
    list_fields = ["code_paths", "tags", "owners", "roster", "repos"]
    for field in list_fields:
        if field in data and isinstance(data[field], list) and data[field]:
            items = ", ".join(str(v) for v in data[field])
            lines.append(f"  {field:12s}: [{items}]")

    # Path
    if "path" in data:
        lines.append(f"  {'path':12s}: {data['path']}")

    # Body summary: show comments and activity counts
    body = data.get("body", "")
    if body:
        comment_count = data.get("_comment_count", 0)
        activity_count = data.get("_activity_count", 0)

        # Extract comments section
        comments_section = ""
        in_comments = False
        for line in body.split("\n"):
            if line.strip() == "## Comments":
                in_comments = True
                continue
            if in_comments:
                if line.startswith("## "):
                    break
                if line.strip():
                    comments_section += line + "\n"

        lines.append("")
        if comments_section.strip():
            lines.append(f"--- Comments ({comment_count}) ---")
            lines.append(comments_section.strip())

        # Show activity log summary (last 5 entries)
        activity_entries = re.findall(
            r"^\s*-\s+(\d{4}-\d{2}-\d{2}):\s+(.+?)(?:\s*$)",
            body, re.MULTILINE
        )
        if activity_entries:
            lines.append("")
            lines.append(f"--- Activity ({activity_count} entries, latest 5) ---")
            for date_str, action in activity_entries[-5:]:
                lines.append(f"  {date_str}  {action.strip()}")

    return "\n".join(lines) + "\n"
