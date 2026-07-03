from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from trailmind.errors import TrailmindError


@dataclass(frozen=True)
class Developer:
    email: str
    shortname: str
    uid: str
    name: str


_REQUIRED_DEVELOPER_KEYS = {"email", "shortname", "uid", "name"}


def _invalid_roster(message: str) -> TrailmindError:
    return TrailmindError(f"invalid roster.yaml: {message}")


def _required_text(raw: object, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field} is required")
    value = raw.strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _normalize_uid(raw: object) -> str:
    if type(raw) is int:
        uid = str(raw)
    elif isinstance(raw, str):
        uid = raw.strip()
    else:
        raise ValueError("uid must be exactly six digits")
    if not uid.isdigit() or len(uid) != 6:
        raise ValueError("uid must be exactly six digits")
    return uid


def _developer_from_item(item: object, index: int) -> Developer:
    if not isinstance(item, Mapping):
        raise _invalid_roster(f"developer #{index} must be a mapping")
    missing_keys = _REQUIRED_DEVELOPER_KEYS.difference(item)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise _invalid_roster(f"developer #{index} missing required field(s): {missing}")
    try:
        email = _required_text(item["email"], "email").lower()
        shortname = _required_text(item["shortname"], "shortname")
        uid = _normalize_uid(item["uid"])
        name = _required_text(item["name"], "name")
    except ValueError as exc:
        raise _invalid_roster(str(exc)) from exc
    return Developer(email=email, shortname=shortname, uid=uid, name=name)


def developer_uid(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"{int(digest[:10], 16) % 1_000_000:06d}"


class Roster:
    def __init__(self, path: Path, developers: list[Developer] | None = None):
        self.path = path
        self.developers = developers or []

    @classmethod
    def load(cls, path: Path) -> "Roster":
        if not path.exists():
            return cls(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _invalid_roster(str(exc)) from exc
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise _invalid_roster(str(exc)) from exc
        data = {} if loaded is None else loaded
        if not isinstance(data, Mapping):
            raise _invalid_roster("top-level document must be a mapping")
        raw_developers = data.get("developers", [])
        if not isinstance(raw_developers, list):
            raise _invalid_roster("developers must be a list")
        roster = cls(path)
        for index, item in enumerate(raw_developers, start=1):
            developer = _developer_from_item(item, index)
            try:
                roster.add(
                    email=developer.email,
                    shortname=developer.shortname,
                    name=developer.name,
                    uid=developer.uid,
                )
            except ValueError as exc:
                raise _invalid_roster(str(exc)) from exc
        return roster

    def add(self, *, email: str, shortname: str, name: str, uid: str | None = None) -> Developer:
        normalized = _required_text(email, "email").lower()
        shortname = _required_text(shortname, "shortname")
        name = _required_text(name, "name")
        if any(dev.email == normalized for dev in self.developers):
            raise ValueError(f"{normalized} is already registered")
        if any(dev.shortname == shortname for dev in self.developers):
            raise ValueError(f"shortname {shortname} is already registered")
        final_uid = developer_uid(normalized) if uid is None else _normalize_uid(uid)
        if any(dev.uid == final_uid for dev in self.developers):
            raise ValueError(f"uid {final_uid} is already registered")
        developer = Developer(email=normalized, shortname=shortname, uid=final_uid, name=name)
        self.developers.append(developer)
        return developer

    def require_shortname(self, email: str) -> str:
        normalized = email.strip().lower()
        for developer in self.developers:
            if developer.email == normalized:
                return developer.shortname
        raise TrailmindError(f"{normalized} is not registered in roster.yaml")

    def resolve_shortname(self, ref: str) -> str:
        """Resolve a reference (email or shortname) to a shortname."""
        normalized = ref.strip().lower()
        for developer in self.developers:
            if developer.email == normalized:
                return developer.shortname
        for developer in self.developers:
            if developer.shortname == normalized:
                return developer.shortname
        raise TrailmindError(f"{ref} is not registered in roster.yaml")

    def require_uid(self, email: str) -> str:
        normalized = email.strip().lower()
        for developer in self.developers:
            if developer.email == normalized:
                return developer.uid
        raise TrailmindError(f"{normalized} is not registered in roster.yaml")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "developers": [
                {"email": dev.email, "shortname": dev.shortname, "uid": dev.uid, "name": dev.name}
                for dev in self.developers
            ]
        }
        self.path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
