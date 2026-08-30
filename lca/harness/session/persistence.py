"""JSONL persistence for SessionStore."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lca.contracts.harness.tasks.session import EventScope, SessionEvent, SessionHeader
from lca.contracts.protocols.session.session_persistence import (
    SessionPersistence,
    SessionPersistenceFactory,
)


class JsonlSessionPersistence(SessionPersistence):
    """Append-only JSONL: first line is the header, rest are events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_header(self, header: SessionHeader) -> None:
        if self.path.exists():
            return
        self.path.write_text(
            json.dumps({"kind": "header", **asdict(header)}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def write_event(self, event: SessionEvent) -> None:
        payload = asdict(event)
        payload["kind"] = "event"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def local_path(self) -> Path:
        return self.path

    def load(self) -> tuple[SessionHeader | None, list[SessionEvent]]:
        if not self.path.exists():
            return None, []
        header: SessionHeader | None = None
        events: list[SessionEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw: dict[str, Any] = json.loads(line)
            kind = raw.pop("kind", "event")
            if kind == "header":
                header = SessionHeader(**{k: raw[k] for k in SessionHeader.__dataclass_fields__})
            elif kind == "event":
                scope_raw = raw.get("scope")
                scope = EventScope(**scope_raw) if isinstance(scope_raw, dict) else None
                events.append(
                    SessionEvent(
                        type=raw["type"],
                        seq=int(raw["seq"]),
                        time=int(raw["time"]),
                        data=raw.get("data") or {},
                        session_id=raw["session_id"],
                        actor=raw.get("actor"),
                        provider=raw.get("provider"),
                        visibility=raw.get("visibility") or "model",
                        scope=scope,
                    )
                )
        return header, events


class JsonlSessionPersistenceFactory(SessionPersistenceFactory):
    """Create JSONL-backed Session persistence below the configured session root."""

    def create(self, *, session_id: str, sessions_dir: Path) -> SessionPersistence:
        return JsonlSessionPersistence(sessions_dir / f"{session_id}.jsonl")


__all__ = [
    "JsonlSessionPersistence",
    "JsonlSessionPersistenceFactory",
]
