from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import SingleQuotedScalarString


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class EntityFormatError(ValueError):
    """Raised when an entity Markdown file has invalid frontmatter."""


def _needs_quote(value: str) -> bool:
    try:
        return yaml.safe_load(value) != value
    except yaml.YAMLError:
        return True


def _coerce(value: Any) -> Any:
    if isinstance(value, str) and _needs_quote(value):
        return SingleQuotedScalarString(value)
    return value


def read_entity(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise EntityFormatError(f"{path}: missing YAML frontmatter")
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise EntityFormatError(f"{path}: malformed YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise EntityFormatError(f"{path}: frontmatter must be a YAML mapping")
    return data, match.group(2)


def _existing_frontmatter(path: Path) -> str | None:
    if not path.exists():
        return None
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def write_entity(path: Path, *, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = _existing_frontmatter(path)
    if original is None:
        frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    else:
        rt_yaml = YAML()
        rt_yaml.preserve_quotes = True
        rt_yaml.width = 1 << 20
        rt_yaml.allow_unicode = True
        rt_yaml.indent(mapping=2, sequence=2, offset=0)
        data = rt_yaml.load(original)
        if not isinstance(data, CommentedMap):
            data = CommentedMap()
        for key, value in frontmatter.items():
            if key in data and data[key] == value:
                continue
            data[key] = _coerce(value)
        for key in list(data.keys()):
            if key not in frontmatter:
                del data[key]
        buffer = io.StringIO()
        rt_yaml.dump(data, buffer)
        frontmatter_text = buffer.getvalue().rstrip("\n")
    path.write_text(f"---\n{frontmatter_text}\n---\n{body}", encoding="utf-8")
