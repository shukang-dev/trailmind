from pathlib import Path

import pytest

from trailmind.errors import TrailmindError
from trailmind.resolver import EntityAmbiguousError, EntityNotFoundError, resolve_entity


def _write_entity(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n---\nbody\n", encoding="utf-8")
    return path


def test_resolve_entity_by_direct_repo_relative_path(tmp_path: Path):
    entity_path = _write_entity(tmp_path / "projects" / "demo" / "mvp" / "tasks" / "T-123456-001-demo.md")

    resolved = resolve_entity(
        tmp_path,
        raw="projects/demo/mvp/tasks/T-123456-001-demo.md",
        entity="T",
    )

    assert resolved == entity_path


def test_resolve_entity_by_bare_id(tmp_path: Path):
    entity_path = _write_entity(tmp_path / "projects" / "demo" / "mvp" / "tasks" / "T-123456-001-demo.md")

    resolved = resolve_entity(tmp_path, raw="T-123456-001", entity="T")

    assert resolved == entity_path


@pytest.mark.parametrize(
    "filename",
    [
        "T-123456-001-.md",
        "T-123456-001--double.md",
        "T-123456-001-Upper.md",
        "T-123456-001-a_b.md",
    ],
)
def test_resolve_entity_by_bare_id_rejects_malformed_slug_suffixes(tmp_path: Path, filename: str):
    _write_entity(tmp_path / "projects" / "demo" / "mvp" / "tasks" / filename)

    with pytest.raises(EntityNotFoundError, match="not found"):
        resolve_entity(tmp_path, raw="T-123456-001", entity="T")


def test_resolve_entity_by_bare_id_rejects_adjacent_id(tmp_path: Path):
    _write_entity(tmp_path / "projects" / "demo" / "mvp" / "tasks" / "T-123456-0010-other.md")

    with pytest.raises(EntityNotFoundError, match="not found"):
        resolve_entity(tmp_path, raw="T-123456-001", entity="T")


def test_resolve_entity_missing_reports_not_found(tmp_path: Path):
    with pytest.raises(EntityNotFoundError, match="not found"):
        resolve_entity(tmp_path, raw="T-123456-001", entity="T")


def test_resolve_entity_ambiguous_reports_candidates(tmp_path: Path):
    first = _write_entity(tmp_path / "projects" / "alpha" / "mvp" / "tasks" / "T-123456-001-alpha.md")
    second = _write_entity(tmp_path / "projects" / "beta" / "mvp" / "tasks" / "T-123456-001-beta.md")

    with pytest.raises(EntityAmbiguousError) as exc_info:
        resolve_entity(tmp_path, raw="T-123456-001", entity="T")

    message = str(exc_info.value)
    assert "ambiguous" in message
    assert message.index(first.relative_to(tmp_path).as_posix()) < message.index(second.relative_to(tmp_path).as_posix())


def test_resolve_entity_rejects_path_escape(tmp_path: Path):
    outside = tmp_path.parent / "T-123456-001-outside.md"
    outside.write_text("---\n---\nbody\n", encoding="utf-8")

    with pytest.raises(TrailmindError, match="not found|outside"):
        resolve_entity(tmp_path, raw=f"../{outside.name}", entity="T")


def test_resolve_entity_rejects_absolute_direct_path_cleanly(tmp_path: Path):
    entity_path = _write_entity(tmp_path / "projects" / "demo" / "mvp" / "tasks" / "T-123456-001-demo.md")

    with pytest.raises(EntityNotFoundError, match="not found"):
        resolve_entity(tmp_path, raw=str(entity_path), entity="T")


def test_resolve_entity_reports_path_resolve_errors_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fail_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path.name == "T-123456-001-demo.md":
            raise RuntimeError("Symlink loop from test")
        return original_resolve(path, *args, **kwargs)

    original_resolve = Path.resolve
    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(TrailmindError, match="not found|could not resolve"):
        resolve_entity(tmp_path, raw="projects/demo/mvp/tasks/T-123456-001-demo.md", entity="T")


def test_resolve_entity_rejects_unsupported_entity_key(tmp_path: Path):
    with pytest.raises(TrailmindError, match="unsupported entity"):
        resolve_entity(tmp_path, raw="X-123456-001", entity="X")
