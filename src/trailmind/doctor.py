from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from trailmind.errors import TrailmindError
from trailmind.log import read_entity_user_facing


@dataclass(frozen=True)
class DoctorFinding:
    severity: str  # "error" or "warning" or "info"
    message: str
    path: str | None = None


def run_doctor(repo_root: Path) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []

    # Check .git directory
    if not (repo_root / ".git").exists():
        findings.append(DoctorFinding(
            severity="warning",
            message="No .git directory found. Trailmind works best in a git repo.",
        ))

    # Check roster.yaml
    roster_path = repo_root / "roster.yaml"
    if not roster_path.exists():
        findings.append(DoctorFinding(
            severity="error",
            message="roster.yaml not found. Run 'trailmind init' or create manually.",
            path="roster.yaml",
        ))
    else:
        try:
            data = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "developers" not in data:
                findings.append(DoctorFinding(
                    severity="error",
                    message="roster.yaml is missing 'developers' key.",
                    path="roster.yaml",
                ))
            elif not isinstance(data["developers"], list):
                findings.append(DoctorFinding(
                    severity="error",
                    message="roster.yaml 'developers' must be a list.",
                    path="roster.yaml",
                ))
        except yaml.YAMLError as exc:
            findings.append(DoctorFinding(
                severity="error",
                message=f"roster.yaml is not valid YAML: {exc}",
                path="roster.yaml",
            ))

    # Check projects directory
    projects_path = repo_root / "projects"
    if not projects_path.exists() or not any(projects_path.iterdir()):
        findings.append(DoctorFinding(
            severity="info",
            message="No projects yet. Run 'trailmind project init' to create one.",
        ))
        return findings

    # Validate entity files
    projects_dir = projects_path
    if projects_dir.exists() and projects_dir.is_dir():
        for project_path in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
            _validate_project(repo_root, project_path, findings)

    # Check for orphaned task references
    _check_task_references(repo_root, findings)

    return findings


def _validate_project(repo_root: Path, project_path: Path, findings: list[DoctorFinding]) -> None:
    project_md = project_path / "PROJECT.md"
    if not project_md.is_file():
        findings.append(DoctorFinding(
            severity="warning",
            message=f"Directory without PROJECT.md: {project_path.name}",
            path=str(project_path.relative_to(repo_root)),
        ))
        return

    try:
        read_entity_user_facing(project_md, label="project")
    except TrailmindError as exc:
        findings.append(DoctorFinding(
            severity="error",
            message=f"Invalid PROJECT.md: {exc}",
            path=str(project_md.relative_to(repo_root)),
        ))

    for epic_path in sorted(e for e in project_path.iterdir() if e.is_dir()):
        _validate_epic(repo_root, epic_path, findings)


def _validate_epic(repo_root: Path, epic_path: Path, findings: list[DoctorFinding]) -> None:
    epic_md = epic_path / "EPIC.md"
    if not epic_md.is_file():
        findings.append(DoctorFinding(
            severity="warning",
            message=f"Directory without EPIC.md: {epic_path.parent.name}/{epic_path.name}",
            path=str(epic_path.relative_to(repo_root)),
        ))
        return

    try:
        read_entity_user_facing(epic_md, label="epic")
    except TrailmindError as exc:
        findings.append(DoctorFinding(
            severity="error",
            message=f"Invalid EPIC.md: {exc}",
            path=str(epic_md.relative_to(repo_root)),
        ))

    # Validate tasks
    tasks_dir = epic_path / "tasks"
    if tasks_dir.is_dir():
        for task_file in sorted(tasks_dir.glob("T-*.md")):
            try:
                fm, _body = read_entity_user_facing(task_file, label="task")
                # Check required fields
                if not fm.get("title"):
                    findings.append(DoctorFinding(
                        severity="warning",
                        message=f"Task missing title: {task_file.stem}",
                        path=str(task_file.relative_to(repo_root)),
                    ))
            except TrailmindError as exc:
                findings.append(DoctorFinding(
                    severity="error",
                    message=f"Invalid task file {task_file.name}: {exc}",
                    path=str(task_file.relative_to(repo_root)),
                ))

    # Validate issues
    issues_dir = epic_path / "issues"
    if issues_dir.is_dir():
        for issue_file in sorted(issues_dir.glob("I-*.md")):
            try:
                read_entity_user_facing(issue_file, label="issue")
            except TrailmindError as exc:
                findings.append(DoctorFinding(
                    severity="error",
                    message=f"Invalid issue file {issue_file.name}: {exc}",
                    path=str(issue_file.relative_to(repo_root)),
                ))

    # Validate milestones
    milestones_dir = epic_path / "milestones"
    if milestones_dir.is_dir():
        for ms_file in sorted(milestones_dir.glob("M-*.md")):
            try:
                read_entity_user_facing(ms_file, label="milestone")
            except TrailmindError as exc:
                findings.append(DoctorFinding(
                    severity="error",
                    message=f"Invalid milestone file {ms_file.name}: {exc}",
                    path=str(ms_file.relative_to(repo_root)),
                ))

    # Validate inbox
    inbox_dir = epic_path / "inbox"
    if inbox_dir.is_dir():
        for inbox_file in sorted(inbox_dir.glob("IN-*.md")):
            try:
                read_entity_user_facing(inbox_file, label="inbox")
            except TrailmindError as exc:
                findings.append(DoctorFinding(
                    severity="error",
                    message=f"Invalid inbox file {inbox_file.name}: {exc}",
                    path=str(inbox_file.relative_to(repo_root)),
                ))


def _check_task_references(repo_root: Path, findings: list[DoctorFinding]) -> None:
    """Check that task dependencies reference existing tasks."""
    projects_path = repo_root / "projects"
    if not projects_path.exists() or not projects_path.is_dir():
        return

    # Collect all task IDs
    all_task_ids: set[str] = set()
    task_files: dict[str, Path] = {}
    for task_file in projects_path.glob("*/*/tasks/T-*.md"):
        if task_file.is_file():
            stem = task_file.stem
            task_id = stem.split("-")[0] + "-" + stem.split("-")[1] + "-" + stem.split("-")[2]
            all_task_ids.add(task_id)
            task_files[task_id] = task_file

    # Check depends_on references
    for task_id, task_path in task_files.items():
        try:
            fm, _body = read_entity_user_facing(task_path, label="task")
        except TrailmindError:
            continue
        for dep_type in ("depends_on", "soft_depends_on"):
            deps = fm.get(dep_type, [])
            if not isinstance(deps, list):
                continue
            for dep in deps:
                dep_str = str(dep)
                if dep_str not in all_task_ids:
                    findings.append(DoctorFinding(
                        severity="warning",
                        message=f"Task {task_id} references non-existent {dep_type}: {dep_str}",
                        path=str(task_path.relative_to(repo_root)),
                    ))


def format_doctor_report(findings: list[DoctorFinding]) -> str:
    if not findings:
        return "All checks passed. Trailmind repo looks healthy.\n"

    lines = ["Trailmind Doctor Report", ""]
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    lines.append(f"Found {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info")
    lines.append("")

    for finding in findings:
        icon = {"error": "ERROR", "warning": "WARN ", "info": "INFO "}[finding.severity]
        path_str = f" ({finding.path})" if finding.path else ""
        lines.append(f"[{icon}] {finding.message}{path_str}")

    return "\n".join(lines) + "\n"
