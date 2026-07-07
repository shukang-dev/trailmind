from pathlib import Path

from click.testing import CliRunner

from trailmind.cli import cli
from trailmind.entity_io import read_entity


def _repo_with_issue(tmp_path: Path) -> tuple[Path, str, str]:
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
    runner.invoke(cli, ["issue", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--title", "Original Issue", "--description", "Something is broken",
                        "--severity", "high"],
                  obj={"cwd": tmp_path})
    issue_files = sorted((tmp_path / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))
    issue_id = issue_files[0].stem.split("-")[0] + "-" + issue_files[0].stem.split("-")[1] + "-" + issue_files[0].stem.split("-")[2]
    return tmp_path, issue_id, "projects/demo/mvp"


def test_issue_clone(tmp_path: Path):
    repo, issue_id, _epic = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/issues/{issue_id}-original-issue.md"
    result = runner.invoke(cli, ["issue", "clone", source_rel, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    issue_files = list((repo / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))
    assert len(issue_files) == 2

    new_issues = [f for f in issue_files if issue_id not in f.stem]
    assert len(new_issues) == 1

    fm, body = read_entity(new_issues[0])
    assert fm["title"] == "Original Issue"
    assert fm["severity"] == "high"
    assert fm["status"] == "open"
    assert "Cloned from" in body


def test_issue_clone_with_new_title(tmp_path: Path):
    repo, issue_id, _epic = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/issues/{issue_id}-original-issue.md"
    result = runner.invoke(cli, ["issue", "clone", source_rel, "--title", "Cloned Bug",
                                 "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    new_issues = list((repo / "projects" / "demo" / "mvp" / "issues").glob("I-*cloned-bug.md"))
    assert len(new_issues) == 1

    fm, _body = read_entity(new_issues[0])
    assert fm["title"] == "Cloned Bug"


def test_issue_clone_to_different_epic(tmp_path: Path):
    repo, issue_id, _epic = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/issues/{issue_id}-original-issue.md"
    result = runner.invoke(cli, ["issue", "clone", source_rel, "--to-epic", "projects/demo/other",
                                 "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    assert len(list((repo / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))) == 1
    assert len(list((repo / "projects" / "demo" / "other" / "issues").glob("I-*.md"))) == 1


def test_issue_clone_with_new_owner(tmp_path: Path):
    repo, issue_id, _epic = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()
    source_rel = f"projects/demo/mvp/issues/{issue_id}-original-issue.md"
    result = runner.invoke(cli, ["issue", "clone", source_rel, "--owner", "bob@example.com",
                                 "--actor", "alice"], obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    issue_files = list((repo / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))
    new_issues = [f for f in issue_files if issue_id not in f.stem]
    assert len(new_issues) == 1
    fm, _body = read_entity(new_issues[0])
    assert fm["owner"] == "bob"


def test_issue_clone_preserves_linked_tasks(tmp_path: Path):
    repo, issue_id, _epic = _repo_with_issue(repo := tmp_path)
    runner = CliRunner()

    # Add a task and link it to the issue
    runner.invoke(cli, ["task", "add", "--epic", "projects/demo/mvp", "--filer", "alice@example.com",
                        "--owner", "alice@example.com", "--title", "Fix Bug", "--priority", "high"],
                  obj={"cwd": repo})
    task_files = sorted((repo / "projects" / "demo" / "mvp" / "tasks").glob("T-*.md"))
    task_id = task_files[0].stem.split("-")[0] + "-" + task_files[0].stem.split("-")[1] + "-" + task_files[0].stem.split("-")[2]
    source_rel = f"projects/demo/mvp/issues/{issue_id}-original-issue.md"
    runner.invoke(cli, ["issue", "link", "--issue", source_rel, "--task", task_id],
                  obj={"cwd": repo})

    result = runner.invoke(cli, ["issue", "clone", source_rel, "--actor", "alice"],
                            obj={"cwd": repo})
    assert result.exit_code == 0, result.output

    issue_files = list((repo / "projects" / "demo" / "mvp" / "issues").glob("I-*.md"))
    new_issues = [f for f in issue_files if issue_id not in f.stem]
    assert len(new_issues) == 1
    fm, _body = read_entity(new_issues[0])
    assert len(fm.get("linked_tasks") or []) > 0
