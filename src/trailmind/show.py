from __future__ import annotations

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

    # List fields
    list_fields = ["code_paths", "depends_on", "soft_depends_on", "known_issues",
                   "deliverables", "completed_deliverables", "linked_tasks",
                   "owners", "tags", "roster", "repos"]
    for field in list_fields:
        if field in data and isinstance(data[field], list) and data[field]:
            items = ", ".join(str(v) for v in data[field])
            lines.append(f"  {field:12s}: [{items}]")

    # Path
    if "path" in data:
        lines.append(f"  {'path':12s}: {data['path']}")

    # Body
    body = data.get("body", "")
    if body:
        lines.append("")
        lines.append("--- Body ---")
        lines.append(body[:500])
        if len(body) > 500:
            lines.append(f"... ({len(body)} chars total)")

    return "\n".join(lines) + "\n"
