from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_task(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."], obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "test", "--title", "Test", "--goal", "Testing",
                        "--roster", "alice", "--repos", "demo"], obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/test", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Original Title",
                        "--code-paths", "src/old.py"], obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id


def test_task_edit_title(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--title", "New Title", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["title"] == "New Title"
    assert "Edited task" in body
    assert "Original Title" in body
    assert "New Title" in body


def test_task_edit_code_paths(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--code-paths", "src/new.py,tests/test_new.py", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["code_paths"] == ["src/new.py", "tests/test_new.py"]


def test_task_edit_design_doc(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--design-doc", "docs/design.md", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["design_doc"] == "docs/design.md"


def test_task_edit_multiple_fields(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--title", "Updated", "--code-paths", "src/a.py",
                                 "--design-doc", "docs/design.md", "--actor", "alice", "--note", "Updated all fields"],
                            obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, body = read_entity(task_file)
    assert fm["title"] == "Updated"
    assert fm["code_paths"] == ["src/a.py"]
    assert fm["design_doc"] == "docs/design.md"
    assert "Updated all fields" in body


def test_task_edit_no_fields_is_error(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_task_edit_clear_design_doc(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    # First set a design doc
    runner.invoke(cli, ["task", "edit", task_id, "--design-doc", "docs/design.md", "--actor", "alice"], obj={"cwd": repo})
    # Then clear it
    result = runner.invoke(cli, ["task", "edit", task_id, "--design-doc", "", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["design_doc"] is None


def test_task_edit_clear_code_paths(tmp_path: Path):
    repo, task_id = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "edit", task_id, "--code-paths", "", "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0

    task_file = sorted((repo / "projects" / "demo" / "test" / "tasks").glob("T-*.md"))[0]
    fm, _body = read_entity(task_file)
    assert fm["code_paths"] == []
