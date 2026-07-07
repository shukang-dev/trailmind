from __future__ import annotations

from pathlib import Path


def build_tree(repo_root: Path) -> dict:
    """Build a tree structure of projects, epics, and entity counts."""
    projects_dir = repo_root / "projects"
    if not projects_dir.exists():
        return {"projects": [], "project_count": 0}

    projects = []
    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        proj_md = proj_dir / "PROJECT.md"
        if not proj_md.exists():
            continue

        proj_info = {"slug": proj_dir.name, "title": proj_dir.name, "state": "active", "epics": []}

        try:
            from trailmind.log import read_entity_user_facing
            fm, _body = read_entity_user_facing(proj_md, label="project")
            proj_info["title"] = str(fm.get("title") or proj_dir.name)
            proj_info["state"] = str(fm.get("state") or "active")
        except Exception:
            pass

        for epic_dir in sorted(proj_dir.iterdir()):
            if not epic_dir.is_dir():
                continue
            epic_md = epic_dir / "EPIC.md"
            if not epic_md.exists():
                continue

            epic_info = {"slug": epic_dir.name, "title": epic_dir.name, "state": "active",
                         "counts": {}, "has_dashboard": (epic_dir / "dashboard.html").exists()}

            try:
                from trailmind.log import read_entity_user_facing
                fm, _body = read_entity_user_facing(epic_md, label="epic")
                epic_info["title"] = str(fm.get("title") or epic_dir.name)
                epic_info["state"] = str(fm.get("state") or "active")
            except Exception:
                pass

            # Count entities
            for label, dir_name in [("tasks", "tasks"), ("issues", "issues"),
                                     ("milestones", "milestones"), ("inbox", "inbox")]:
                d = epic_dir / dir_name
                if d.exists():
                    count = len([f for f in d.iterdir() if f.is_file() and f.suffix == ".md"])
                    if count > 0:
                        epic_info["counts"][label] = count

            for label, dir_name in [("specs", "specs"), ("plans", "plans")]:
                d = epic_dir / "docs" / dir_name
                if d.exists():
                    count = len([f for f in d.iterdir() if f.is_file() and f.suffix == ".md"])
                    if count > 0:
                        epic_info["counts"][label] = count

            proj_info["epics"].append(epic_info)

        proj_info["epic_count"] = len(proj_info["epics"])
        projects.append(proj_info)

    return {"projects": projects, "project_count": len(projects)}


def format_tree(tree: dict) -> str:
    """Format the tree as a human-readable text tree."""
    lines = []
    lines.append(f"projects/ ({tree.get('project_count', 0)} projects)")

    for pi, proj in enumerate(tree["projects"]):
        is_last_proj = pi == len(tree["projects"]) - 1
        proj_prefix = "└── " if is_last_proj else "├── "
        proj_continuation = "    " if is_last_proj else "│   "

        state_str = f" [{proj['state']}]" if proj.get("state") else ""
        lines.append(f"{proj_prefix}📦 {proj['slug']}{state_str} — {proj['title']}")

        epics = proj["epics"]
        for ei, epic in enumerate(epics):
            is_last_epic = ei == len(epics) - 1
            epic_prefix = "└── " if is_last_epic else "├── "
            epic_continuation = "    " if is_last_epic else "│   "

            state_str = f" [{epic['state']}]" if epic.get("state") else ""
            dash_str = " 📊" if epic.get("has_dashboard") else ""
            lines.append(f"{proj_continuation}{epic_prefix}🎯 {epic['slug']}{state_str}{dash_str} — {epic['title']}")

            # Entity counts
            counts = epic.get("counts", {})
            if counts:
                count_parts = []
                icons = {"tasks": "✅", "issues": "🐛", "milestones": "🏁",
                         "inbox": "📥", "specs": "📐", "plans": "📋"}
                for label, count in counts.items():
                    icon = icons.get(label, "📄")
                    count_parts.append(f"{icon} {count} {label}")

                # Show counts on one line
                count_line = "  ".join(count_parts)
                deeper_continuation = proj_continuation + ("    " if is_last_epic else "│   ")
                lines.append(f"{deeper_continuation}    {count_line}")

    return "\n".join(lines)
