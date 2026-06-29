from __future__ import annotations

import io
import re
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
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


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _coerce_tree(value: Any) -> Any:
    if isinstance(value, str):
        return _coerce(value)
    if isinstance(value, Mapping):
        mapped = CommentedMap()
        for key, item in value.items():
            mapped[key] = _coerce_tree(item)
        return mapped
    if _is_sequence(value):
        seq = CommentedSeq()
        seq.extend(_coerce_tree(item) for item in value)
        return seq
    return value


def _overlay_value(existing: Any, desired: Any) -> Any:
    if isinstance(desired, str):
        if existing == desired and not _needs_quote(desired):
            return existing
        return _coerce(desired)
    if isinstance(desired, Mapping) and isinstance(existing, MutableMapping):
        for key, item in desired.items():
            if key in existing:
                new_value = _overlay_value(existing[key], item)
                if new_value is not existing[key]:
                    existing[key] = new_value
            else:
                existing[key] = _coerce_tree(item)
        for key in list(existing.keys()):
            if key not in desired:
                del existing[key]
        return existing
    if _is_sequence(desired) and isinstance(existing, MutableSequence) and len(existing) == len(desired):
        for index, item in enumerate(desired):
            new_value = _overlay_value(existing[index], item)
            if new_value is not existing[index]:
                existing[index] = new_value
        return existing
    if existing == desired:
        return existing
    return _coerce_tree(desired)


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
            if key in data:
                new_value = _overlay_value(data[key], value)
                if new_value is not data[key]:
                    data[key] = new_value
            else:
                data[key] = _coerce_tree(value)
        for key in list(data.keys()):
            if key not in frontmatter:
                del data[key]
        buffer = io.StringIO()
        rt_yaml.dump(data, buffer)
        frontmatter_text = buffer.getvalue().rstrip("\n")
    path.write_text(f"---\n{frontmatter_text}\n---\n{body}", encoding="utf-8")
