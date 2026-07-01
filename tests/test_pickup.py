import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity, write_entity
from trailmind.errors import TrailmindError
from trailmind.pickup import (
    PickupPack,
    build_base_pickup_pack,
    build_task_pickup,
    excerpt_file,
    extract_activity_entries,
    extract_markdown_section,
    format_pickup_markdown,
    pickup_pack_to_dict,
)


def test_extract_markdown_section_returns_named_section_body():
    body = "# Title\n\n## Scope\n\nBuild it.\n\n## Acceptance\n\n- Works\n\n## Activity Log\n\n- entry\n"

    assert extract_markdown_section(body, "Scope") == "Build it."
    assert extract_markdown_section(body, "Acceptance") == "- Works"
    assert extract_markdown_section(body, "Missing") is None


def test_extract_markdown_section_strips_heading_whitespace():
    indented_heading = "# Title\n\n  ## Scope  \n\nBuild it.\n"
    indented_next_heading = "# Title\n\n## Scope\n\nBuild it.\n\n  ## Acceptance  \n\n- Works\n"

    assert extract_markdown_section(indented_heading, "Scope") == "Build it."
    assert extract_markdown_section(indented_next_heading, "Scope") == "Build it."


def test_extract_activity_entries_returns_recent_entries():
    body = (
        "# Task\n\n"
        "## Activity Log\n\n"
        "- 2026-07-01: First.\n"
        "- 2026-07-02: Second.\n"
        "- 2026-07-03: Third.\n"
    )

    assert extract_activity_entries(body, limit=2) == [
        "- 2026-07-02: Second.",
        "- 2026-07-03: Third.",
    ]


def test_extract_activity_entries_rejects_non_positive_limit():
    with pytest.raises(TrailmindError, match="activity limit must be at least 1"):
        extract_activity_entries("## Activity Log\n\n- entry\n", limit=0)


def test_excerpt_file_truncates_text_files(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    excerpt = excerpt_file(tmp_path, "src/app.py", max_lines=2)

    assert excerpt["path"] == "src/app.py"
    assert excerpt["start_line"] == 1
    assert excerpt["end_line"] == 2
    assert excerpt["total_lines"] == 3
    assert excerpt["truncated"] is True
    assert excerpt["content"] == "one\ntwo"
    assert excerpt["skipped"] is False


def test_excerpt_file_does_not_call_read_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    def fail_read_text(self, *args, **kwargs):
        raise AssertionError("read_text should not be used for excerpts")

    monkeypatch.setattr(type(target), "read_text", fail_read_text)

    excerpt = excerpt_file(tmp_path, "src/app.py", max_lines=2)

    assert excerpt["total_lines"] == 3
    assert excerpt["content"] == "one\ntwo"


def test_excerpt_file_reports_missing_files(tmp_path: Path):
    excerpt = excerpt_file(tmp_path, "src/missing.py", max_lines=80)

    assert excerpt["path"] == "src/missing.py"
    assert excerpt["skipped"] is True
    assert excerpt["skip_reason"] == "missing"


def test_excerpt_file_rejects_path_escape(tmp_path: Path):
    with pytest.raises(TrailmindError, match="referenced path escapes repository"):
        excerpt_file(tmp_path, "../secret.txt", max_lines=80)


def test_excerpt_file_rejects_non_positive_max_lines(tmp_path: Path):
    with pytest.raises(TrailmindError, match="max lines must be at least 1"):
        excerpt_file(tmp_path, "src/app.py", max_lines=0)


def test_base_pickup_pack_dict_shape():
    pack = build_base_pickup_pack(kind="task", repo_path="projects/demo/mvp/tasks/T-123456-001-demo.md")

    data = pickup_pack_to_dict(pack)

    assert data["kind"] == "task"
    assert data["item"]["path"] == "projects/demo/mvp/tasks/T-123456-001-demo.md"
    assert data["dependencies"] == {}
    assert data["linked_items"] == {}
    assert data["deliverables"] == {}
    assert data["activity"] == []
    assert data["excerpts"] == []
    assert data["next_actions"] == []
    assert data["warnings"] == []


def _repo_with_task(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n"
        "  shortname: alice\n"
        "  uid: '123456'\n"
        "  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    assert runner.invoke(
        cli,
        [
            "project",
            "init",
            "--slug",
            "demo_app",
            "--title",
            "Demo App",
            "--goal",
            "Build a useful demo.",
        ],
        obj={"cwd": tmp_path},
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "mvp",
            "--title",
            "MVP",
            "--goal",
            "First usable release",
        ],
        obj={"cwd": tmp_path},
    ).exit_code == 0
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('one')\nprint('two')\n", encoding="utf-8")
    result = runner.invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build parser",
            "--code-paths",
            "src/app.py",
            "--deliverables",
            "tests pass",
        ],
        obj={"cwd": tmp_path},
    )
    assert result.exit_code == 0
    return tmp_path


def _task_path(repo: Path) -> Path:
    return repo / "projects" / "demo_app" / "mvp" / "tasks" / "T-123456-001-build-parser.md"


def test_task_pickup_cli_prints_markdown(tmp_path: Path):
    repo = _repo_with_task(tmp_path)

    result = CliRunner().invoke(cli, ["task", "pickup", "T-123456-001"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "# Task Pickup: T-123456-001 Build parser" in result.output
    assert "## Next Actions" in result.output


def test_task_pickup_cli_prints_json(tmp_path: Path):
    repo = _repo_with_task(tmp_path)

    result = CliRunner().invoke(cli, ["task", "pickup", "T-123456-001", "--json"], obj={"cwd": repo})

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kind"] == "task"
    assert data["item"]["id"] == "T-123456-001"
    assert data["excerpts"][0]["path"] == "src/app.py"


def test_task_pickup_no_excerpts_lists_paths_without_file_content(tmp_path: Path):
    repo = _repo_with_task(tmp_path)

    result = CliRunner().invoke(cli, ["task", "pickup", "T-123456-001", "--no-excerpts"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "src/app.py" in result.output
    assert "skipped: excluded" in result.output
    assert "print('one')" not in result.output


def test_task_pickup_log_requires_actor_without_modifying_file(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    before = _task_path(repo).read_text(encoding="utf-8")

    result = CliRunner().invoke(cli, ["task", "pickup", "T-123456-001", "--log"], obj={"cwd": repo})

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "pickup logging requires --actor" in result.output
    assert _task_path(repo).read_text(encoding="utf-8") == before


def test_task_pickup_json_log_rejects_blank_actor_before_printing_pack(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    before = _task_path(repo).read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["task", "pickup", "T-123456-001", "--json", "--log", "--actor", "   "],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "pickup logging requires --actor" in result.output
    assert not result.output.lstrip().startswith("{")
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.output)
    assert _task_path(repo).read_text(encoding="utf-8") == before


def test_task_pickup_log_records_one_activity_entry(tmp_path: Path):
    repo = _repo_with_task(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["task", "pickup", "T-123456-001", "--log", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    frontmatter, body = read_entity(_task_path(repo))
    assert frontmatter["status"] == "created"
    assert body.count("Picked up for handoff by alice.") == 1


def test_build_task_pickup_includes_task_summary_activity_and_excerpt(tmp_path: Path):
    repo = _repo_with_task(tmp_path)

    pack = build_task_pickup(repo, task_ref="T-123456-001", max_lines=1, activity_limit=10, include_excerpts=True)

    assert pack.kind == "task"
    assert pack.item["id"] == "T-123456-001"
    assert pack.item["title"] == "Build parser"
    assert pack.item["status"] == "created"
    assert pack.deliverables["missing"] == ["tests pass"]
    assert pack.excerpts[0]["path"] == "src/app.py"
    assert pack.excerpts[0]["content"] == "print('one')"
    assert "Task is ready to start." in pack.next_actions


def test_format_task_pickup_markdown_uses_predictable_sections(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    pack = build_task_pickup(repo, task_ref="T-123456-001", max_lines=1, activity_limit=10, include_excerpts=True)

    rendered = format_pickup_markdown(pack)

    assert "# Task Pickup: T-123456-001 Build parser" in rendered
    assert "## Summary" in rendered
    assert "## Current State" in rendered
    assert "## Deliverables" in rendered
    assert "## Relevant Files" in rendered
    assert "src/app.py" in rendered
    assert "## Next Actions" in rendered


def test_format_pickup_markdown_uses_fence_longer_than_embedded_backticks():
    pack = PickupPack(
        kind="task",
        generated_at="2026-07-01",
        item={
            "id": "T-123456-001",
            "title": "Design review",
            "path": "projects/demo_app/mvp/tasks/T-123456-001-design-review.md",
            "status": "created",
            "scope": "Review the design doc.",
        },
        excerpts=[
            {
                "path": "docs/design.md",
                "content": "Before\n```\ncode\n```\nAfter",
                "skipped": False,
            }
        ],
    )

    rendered = format_pickup_markdown(pack)

    assert "### docs/design.md\n````\nBefore\n```\ncode\n```\nAfter\n````" in rendered


def test_build_task_pickup_is_read_only_by_default(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    before = _task_path(repo).read_text(encoding="utf-8")

    build_task_pickup(repo, task_ref="T-123456-001", max_lines=80, activity_limit=10, include_excerpts=True)

    assert _task_path(repo).read_text(encoding="utf-8") == before


def test_build_task_pickup_prefers_local_known_issue_when_duplicate_id_exists(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    runner = CliRunner()
    assert runner.invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "next",
            "--title",
            "Next",
            "--goal",
            "Follow-up release",
        ],
        obj={"cwd": repo},
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--title",
            "Parser issue",
            "--description",
            "Parser issue details.",
            "--severity",
            "medium",
        ],
        obj={"cwd": repo},
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            "projects/demo_app/next",
            "--filer",
            "alice@example.com",
            "--title",
            "Other epic issue",
            "--description",
            "Other epic issue details.",
            "--severity",
            "medium",
        ],
        obj={"cwd": repo},
    ).exit_code == 0
    link_result = runner.invoke(
        cli,
        [
            "issue",
            "link",
            "--issue",
            "projects/demo_app/mvp/issues/I-123456-001-parser-issue.md",
            "--task",
            "T-123456-001",
        ],
        obj={"cwd": repo},
    )
    assert link_result.exit_code == 0
    task_frontmatter, _body = read_entity(_task_path(repo))
    assert task_frontmatter["known_issues"] == ["I-123456-001"]

    pack = build_task_pickup(repo, task_ref="T-123456-001", max_lines=80, activity_limit=10, include_excerpts=True)

    assert pack.linked_items["issues"] == [
        {
            "id": "I-123456-001",
            "title": "Parser issue",
            "status": "open",
            "path": "projects/demo_app/mvp/issues/I-123456-001-parser-issue.md",
        }
    ]
    assert not any(warning.startswith("linked issue I-123456-001:") for warning in pack.warnings)


def test_task_pickup_reports_hard_dependency_blocker(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build UI",
            "--depends-on",
            "T-123456-001",
        ],
        obj={"cwd": repo},
    )
    assert result.exit_code == 0

    pack = build_task_pickup(repo, task_ref="T-123456-002", max_lines=80, activity_limit=10, include_excerpts=False)

    assert pack.dependencies["hard"][0]["task_id"] == "T-123456-001"
    assert "Hard dependencies are not terminal; do not start implementation yet." in pack.next_actions


def test_task_pickup_reports_soft_dependency_warning(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Build UI",
            "--soft-depends-on",
            "T-123456-001",
        ],
        obj={"cwd": repo},
    )
    assert result.exit_code == 0

    pack = build_task_pickup(repo, task_ref="T-123456-002", max_lines=80, activity_limit=10, include_excerpts=False)

    assert pack.dependencies["soft"][0]["task_id"] == "T-123456-001"
    assert "T-123456-001 soft dependency is created" in pack.warnings


def test_task_pickup_reports_linked_open_issue(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    runner = CliRunner()
    issue = runner.invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--title",
            "Parser bug",
            "--description",
            "Parser fails on flags.",
            "--severity",
            "high",
        ],
        obj={"cwd": repo},
    )
    assert issue.exit_code == 0
    link = runner.invoke(cli, ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"], obj={"cwd": repo})
    assert link.exit_code == 0

    pack = build_task_pickup(repo, task_ref="T-123456-001", max_lines=80, activity_limit=10, include_excerpts=False)

    assert pack.linked_items["issues"][0]["id"] == "I-123456-001"
    assert "Review linked open issues before closing the task." in pack.next_actions


def test_task_pickup_terminal_task_hint(tmp_path: Path):
    repo = _repo_with_task(tmp_path)
    task_path = _task_path(repo)
    frontmatter, body = read_entity(task_path)
    frontmatter["status"] = "done"
    write_entity(task_path, frontmatter=frontmatter, body=body)

    pack = build_task_pickup(repo, task_ref="T-123456-001", max_lines=80, activity_limit=10, include_excerpts=False)

    assert pack.next_actions == [
        "Task is terminal (done); do not pick it up for implementation unless reopening is intentional."
    ]


def _repo_with_issue(tmp_path: Path) -> Path:
    repo = _repo_with_task(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "issue",
            "add",
            "--epic",
            "projects/demo_app/mvp",
            "--filer",
            "alice@example.com",
            "--title",
            "Parser bug",
            "--description",
            "Parser fails on flags.",
            "--severity",
            "high",
        ],
        obj={"cwd": repo},
    )
    assert result.exit_code == 0
    return repo


def _issue_path(repo: Path) -> Path:
    return repo / "projects" / "demo_app" / "mvp" / "issues" / "I-123456-001-parser-bug.md"


def test_issue_pickup_cli_prints_markdown(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001"], obj={"cwd": repo})

    assert result.exit_code == 0
    assert "# Issue Pickup: I-123456-001 Parser bug" in result.output
    assert "## Linked Tasks" in result.output
    assert "## Dependencies" not in result.output
    assert "## Deliverables" not in result.output
    assert "## Linked Issues" not in result.output
    assert "Parser fails on flags." in result.output


def test_issue_pickup_cli_prints_json(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--json"], obj={"cwd": repo})

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kind"] == "issue"
    assert data["item"]["id"] == "I-123456-001"
    assert data["item"]["severity"] == "high"
    assert "Decide whether to link this issue to a task, carry it forward, or close it." in data["next_actions"]


def test_issue_pickup_reports_linked_task(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    link = CliRunner().invoke(cli, ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"], obj={"cwd": repo})
    assert link.exit_code == 0

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--json", "--no-excerpts"], obj={"cwd": repo})

    data = json.loads(result.output)
    assert data["linked_items"]["tasks"][0]["task_id"] == "T-123456-001"
    assert data["excerpts"][0] == {"path": "src/app.py", "skipped": True, "skip_reason": "excluded"}
    assert "Inspect linked task state before closing the issue." in data["next_actions"]


def test_issue_pickup_prefers_local_linked_task_when_duplicate_id_exists(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    runner = CliRunner()
    link = runner.invoke(
        cli,
        ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"],
        obj={"cwd": repo},
    )
    assert link.exit_code == 0
    assert runner.invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "demo_app",
            "--slug",
            "next",
            "--title",
            "Next",
            "--goal",
            "Follow-up release",
        ],
        obj={"cwd": repo},
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "task",
            "add",
            "--epic",
            "projects/demo_app/next",
            "--filer",
            "alice@example.com",
            "--owner",
            "alice@example.com",
            "--title",
            "Other parser",
        ],
        obj={"cwd": repo},
    ).exit_code == 0

    result = runner.invoke(cli, ["issue", "pickup", "I-123456-001", "--json", "--no-excerpts"], obj={"cwd": repo})

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["linked_items"]["tasks"] == [
        {
            "ref": "T-123456-001",
            "task_id": "T-123456-001",
            "title": "Build parser",
            "status": "created",
            "terminal": False,
            "path": "projects/demo_app/mvp/tasks/T-123456-001-build-parser.md",
            "code_paths": ["src/app.py"],
        }
    ]
    assert not data["warnings"]


def test_issue_pickup_warns_and_skips_linked_task_with_malformed_code_paths(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    link = CliRunner().invoke(cli, ["issue", "link", "--issue", "I-123456-001", "--task", "T-123456-001"], obj={"cwd": repo})
    assert link.exit_code == 0
    task_path = _task_path(repo)
    frontmatter, body = read_entity(task_path)
    frontmatter["code_paths"] = "src/app.py"
    write_entity(task_path, frontmatter=frontmatter, body=body)

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--json"], obj={"cwd": repo})

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["linked_items"]["tasks"] == []
    assert data["warnings"] == ["linked task T-123456-001: task field code_paths must be a list"]


def test_issue_pickup_terminal_issue_hint(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    issue_path = _issue_path(repo)
    frontmatter, body = read_entity(issue_path)
    frontmatter["status"] = "done"
    write_entity(issue_path, frontmatter=frontmatter, body=body)

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--json"], obj={"cwd": repo})

    data = json.loads(result.output)
    assert data["next_actions"] == ["Issue is terminal (done); only pick it up if reopening is intentional."]


def test_issue_pickup_reports_carried_metadata(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    issue_path = _issue_path(repo)
    frontmatter, body = read_entity(issue_path)
    frontmatter["carried_into"] = ["projects/demo_app/mvp"]
    write_entity(issue_path, frontmatter=frontmatter, body=body)

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--json"], obj={"cwd": repo})

    data = json.loads(result.output)
    assert data["item"]["frontmatter"]["carried_into"] == ["projects/demo_app/mvp"]
    assert "Inspect carried-into epics before changing issue status." in data["next_actions"]


def test_issue_pickup_log_records_one_activity_entry(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["issue", "pickup", "I-123456-001", "--log", "--actor", "alice"],
        obj={"cwd": repo},
    )

    assert result.exit_code == 0
    _frontmatter, body = read_entity(_issue_path(repo))
    assert body.count("Picked up for handoff by alice.") == 1


def test_issue_pickup_log_requires_actor_without_modifying_file(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    before = _issue_path(repo).read_text(encoding="utf-8")

    result = CliRunner().invoke(cli, ["issue", "pickup", "I-123456-001", "--log"], obj={"cwd": repo})

    assert result.exit_code == 1
    assert "pickup logging requires --actor" in result.output
    assert _issue_path(repo).read_text(encoding="utf-8") == before


def test_issue_pickup_json_log_rejects_blank_actor_before_printing_pack(tmp_path: Path):
    repo = _repo_with_issue(tmp_path)
    before = _issue_path(repo).read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["issue", "pickup", "I-123456-001", "--json", "--log", "--actor", "   "],
        obj={"cwd": repo},
    )

    assert result.exit_code == 1
    assert "pickup logging requires --actor" in result.output
    assert not result.output.lstrip().startswith("{")
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.output)
    assert _issue_path(repo).read_text(encoding="utf-8") == before
