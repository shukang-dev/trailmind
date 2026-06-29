import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity
from trailmind.errors import TrailmindError
from trailmind.paths import epic_dir, project_dir


def _remove_if_created(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def test_project_init_creates_project_files(tmp_path: Path):
    (tmp_path / ".git").mkdir()

    result = CliRunner().invoke(
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
            "--owners",
            "alice@example.com",
            "--tags",
            "demo,agent",
        ],
        obj={"cwd": tmp_path},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/PROJECT.md" in result.output
    assert "projects/demo_app/AGENTS.md" in result.output

    project_path = tmp_path / "projects" / "demo_app" / "PROJECT.md"
    agents_path = tmp_path / "projects" / "demo_app" / "AGENTS.md"
    assert project_path.exists()
    assert agents_path.exists()

    frontmatter, body = read_entity(project_path)
    assert frontmatter["slug"] == "demo_app"
    assert frontmatter["owners"] == ["alice@example.com"]
    assert frontmatter["tags"] == ["demo", "agent"]
    assert "Demo App" in body
    assert "Project demo_app" in agents_path.read_text(encoding="utf-8")


def test_epic_init_creates_epic_tree(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    project_result = runner.invoke(
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
    )
    assert project_result.exit_code == 0

    result = runner.invoke(
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
            "--start",
            "2026-06-29",
            "--target",
            "2026-07-15",
            "--roster",
            "alice",
            "--repos",
            "demo_app",
        ],
        obj={"cwd": tmp_path},
    )

    assert result.exit_code == 0
    assert "projects/demo_app/mvp/EPIC.md" in result.output
    assert "projects/demo_app/mvp/AGENTS.md" in result.output

    epic_dir = tmp_path / "projects" / "demo_app" / "mvp"
    epic_path = epic_dir / "EPIC.md"
    agents_path = epic_dir / "AGENTS.md"
    assert epic_path.exists()
    assert agents_path.exists()
    assert (epic_dir / "tasks").is_dir()
    assert (epic_dir / "issues").is_dir()
    assert (epic_dir / "milestones").is_dir()
    assert (epic_dir / "docs" / "specs").is_dir()
    assert (epic_dir / "docs" / "plans").is_dir()

    frontmatter, body = read_entity(epic_path)
    assert frontmatter["slug"] == "mvp"
    assert frontmatter["project"] == "demo_app"
    assert frontmatter["state"] == "active"
    assert frontmatter["roster"] == ["alice"]
    assert frontmatter["repos"] == ["demo_app"]
    assert frontmatter["carried_issues"] == []
    assert "MVP" in body
    assert "First usable release" in body


def test_epic_init_rejects_missing_project(tmp_path: Path):
    (tmp_path / ".git").mkdir()

    result = CliRunner().invoke(
        cli,
        [
            "epic",
            "init",
            "--project",
            "missing",
            "--slug",
            "mvp",
            "--title",
            "MVP",
            "--goal",
            "First usable release",
        ],
        obj={"cwd": tmp_path},
    )

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "project missing does not exist" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("slug", ["", ".", "..", "nested/path", r"nested\path", "../escape"])
def test_project_dir_rejects_unsafe_slug_components(tmp_path: Path, slug: str):
    with pytest.raises(TrailmindError, match="project slug"):
        project_dir(tmp_path, slug)


def test_project_dir_rejects_absolute_slug_component(tmp_path: Path):
    absolute_slug = str(tmp_path.parent / "absolute_escape")

    with pytest.raises(TrailmindError, match="project slug"):
        project_dir(tmp_path, absolute_slug)


@pytest.mark.parametrize(
    ("project", "slug", "message"),
    [
        ("../project", "mvp", "project slug"),
        ("demo_app", "", "epic slug"),
        ("demo_app", ".", "epic slug"),
        ("demo_app", "..", "epic slug"),
        ("demo_app", "nested/path", "epic slug"),
        ("demo_app", r"nested\path", "epic slug"),
        ("demo_app", "../escape_epic", "epic slug"),
    ],
)
def test_epic_dir_rejects_unsafe_slug_components(
    tmp_path: Path,
    project: str,
    slug: str,
    message: str,
):
    with pytest.raises(TrailmindError, match=message):
        epic_dir(tmp_path, project, slug)


def test_project_init_rejects_traversal_slug_without_creating_outside_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    outside_project = tmp_path.parent / "escape"
    _remove_if_created(outside_project)

    try:
        result = CliRunner().invoke(
            cli,
            [
                "project",
                "init",
                "--slug",
                "../../escape",
                "--title",
                "Escape",
                "--goal",
                "Should not be written.",
            ],
            obj={"cwd": tmp_path},
        )

        assert result.exit_code == 1
        assert "error:" in result.output
        assert "Traceback" not in result.output
        assert not outside_project.exists()
    finally:
        _remove_if_created(outside_project)


def test_epic_init_rejects_traversal_slug_without_creating_outside_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    project_result = runner.invoke(
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
    )
    assert project_result.exit_code == 0
    outside_epic = tmp_path.parent / "escape_epic"
    _remove_if_created(outside_epic)

    try:
        result = runner.invoke(
            cli,
            [
                "epic",
                "init",
                "--project",
                "demo_app",
                "--slug",
                "../../../escape_epic",
                "--title",
                "Escape Epic",
                "--goal",
                "Should not be written.",
            ],
            obj={"cwd": tmp_path},
        )

        assert result.exit_code == 1
        assert "error:" in result.output
        assert "Traceback" not in result.output
        assert not outside_epic.exists()
    finally:
        _remove_if_created(outside_epic)


def test_project_init_rejects_absolute_slug_cleanly_without_creating_outside_repo(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    outside_project = tmp_path.parent / f"{tmp_path.name}_absolute_escape"
    _remove_if_created(outside_project)

    try:
        result = CliRunner().invoke(
            cli,
            [
                "project",
                "init",
                "--slug",
                str(outside_project),
                "--title",
                "Absolute Escape",
                "--goal",
                "Should not be written.",
            ],
            obj={"cwd": tmp_path},
        )

        assert result.exit_code == 1
        assert "error:" in result.output
        assert "Traceback" not in result.output
        assert not outside_project.exists()
    finally:
        _remove_if_created(outside_project)
