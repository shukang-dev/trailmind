from __future__ import annotations

import hashlib
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
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_developers = data.get("developers", [])
        developers = [
            Developer(
                email=str(item["email"]),
                shortname=str(item["shortname"]),
                uid=f"{int(item['uid']):06d}" if isinstance(item["uid"], int) else str(item["uid"]),
                name=str(item["name"]),
            )
            for item in raw_developers
        ]
        return cls(path, developers)

    def add(self, *, email: str, shortname: str, name: str, uid: str | None = None) -> Developer:
        normalized = email.strip().lower()
        if any(dev.email == normalized for dev in self.developers):
            raise ValueError(f"{normalized} is already registered")
        if any(dev.shortname == shortname for dev in self.developers):
            raise ValueError(f"shortname {shortname} is already registered")
        final_uid = uid or developer_uid(normalized)
        if not final_uid.isdigit() or len(final_uid) != 6:
            raise ValueError("uid must be exactly six digits")
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
