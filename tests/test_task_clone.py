from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_task(tmp_path: Path) -> tuple[Path, str, str]:
    (tmp_path / ".git").mkdir()
    (tmp_path / "roster.yaml").write_text(
        "developers:\n"
        "- email: alice@example.com\n  shortname: alice\n  uid: '123456'\n  name: Alice\n"
        "- email: bob@example.com\n  shortname: bob\n  uid: '654321'\n  name: Bob\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    runner.invoke(cli, ["project", "init", "--slug", "demo", "--title", "Demo", "--goal", "Test."],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "mvp", "--title", "MVP",
                        "--goal", "Ship.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["epic", "init", "--project", "demo", "--slug", "other", "--title", "Other",
                        "--goal", "Other.", "--roster", "alice", "--repos", "demo"],
                  obj={"cwd": tmp_path})
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Original Task",
                        "--priority", "high", "--code-paths", "src/app.py,src/utils.py",
                        "--deliverables", "tests pass,docs updated"],
                  obj={"cwd": tmp_path})
    task_files = sorted((tmp_path / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    return tmp_path, task_id, "projects/demo/mvp"


def test_task_clone(tmp_path: Path):
    repo, task_id, _epic = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    # Use relative path to avoid ambiguity
    source_rel = f"projects/demo/mvp/tasks/{task_id}-original-task.md"
    result = runner.invoke(cli, ["task", "clone", source_rel, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    # Should have 2 tasks now
    task_files = list((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    assert len(task_files) == 2

    # New task should have same title but different ID
    new_tasks = [f for f in task_files if task_id not in f.stem]
    assert len(new_tasks) == 1

    fm, body = read_entity(new_tasks[0])
    assert fm["title"] == "Original Task"
    assert fm["priority"] == "high"
    assert fm["status"] == "created"
    assert fm["code_paths"] == ["src/app.py", "src/utils.py"]
    assert fm["deliverables"] == ["tests pass", "docs updated"]
    assert "Cloned from" in body


def test_task_clone_with_new_title(tmp_path: Path):
    repo, task_id, _epic = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/tasks/{task_id}-original-task.md"
    result = runner.invoke(cli, ["task", "clone", source_rel, "--title", "Cloned Variant", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    task_files = list((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    new_task = [f for f in task_files if "cloned-variant" in f.name]
    assert len(new_task) == 1

    fm, _body = read_entity(new_task[0])
    assert fm["title"] == "Cloned Variant"


def test_task_clone_to_different_epic(tmp_path: Path):
    repo, task_id, _epic = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/tasks/{task_id}-original-task.md"
    result = runner.invoke(cli, ["task", "clone", source_rel, "--to-epic", "projects/demo/other", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    # Source epic should still have 1 task
    assert len(list((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))) == 1
    # Target epic should have 1 task
    assert len(list((repo / "projects" / "demo" / "other" / "tasks").glob("T-*.md"))) == 1


def test_task_clone_with_new_owner(tmp_path: Path):
    repo, task_id, _epic = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/tasks/{task_id}-original-task.md"
    result = runner.invoke(cli, ["task", "clone", source_rel, "--owner", "bob@example.com", "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    task_files = list((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    new_tasks = [f for f in task_files if task_id not in f.stem]
    assert len(new_tasks) == 1
    fm, _body = read_entity(new_tasks[0])
    assert fm["owner"] == "bob"


def test_task_clone_preserves_design_doc(tmp_path: Path):
    repo, task_id, _epic = _repo_with_task(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/tasks/{task_id}-original-task.md"
    # Add design doc to source task
    runner.invoke(cli, ["task", "edit", source_rel, "--design-doc", "docs/design.md", "--actor", "alice"],
                  obj={"cwd": repo})

    result = runner.invoke(cli, ["task", "clone", source_rel, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    task_files = list((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    new_tasks = [f for f in task_files if task_id not in f.stem]
    assert len(new_tasks) == 1
    fm, _body = read_entity(new_tasks[0])
    assert fm["design_doc"] == "docs/design.md"
