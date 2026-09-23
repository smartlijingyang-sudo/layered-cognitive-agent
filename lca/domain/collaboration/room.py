"""Collaboration Room specification repository and message routing (ADR-0250).

Provides RoomSpec persistence (JsonRoomRepository) and dynamic room-level message routing policies
(coordinator_first vs mention_only) without hardcoded role dictionaries.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from lca.contracts.models.collaboration.peer import RoomMessage, RoomSpec
from lca.infrastructure.path.locator import get_lca_home

_logger = logging.getLogger(__name__)


class RoomRepository(Protocol):
    """Protocol for RoomSpec persistence."""

    def save(self, room: RoomSpec) -> None: ...
    def get(self, room_id: str) -> RoomSpec | None: ...
    def list_rooms(self) -> tuple[RoomSpec, ...]: ...
    def delete(self, room_id: str) -> bool: ...


class JsonRoomRepository(RoomRepository):
    """File-backed RoomRepository persisting under ~/.lca/rooms/."""

    def __init__(self, base_dir: Path | None = None) -> None:
        root = base_dir or get_lca_home()
        self._dir = root / "rooms"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, room: RoomSpec) -> None:
        """Persist room specification as JSON."""
        target = self._dir / f"{room.room_id}.json"
        target.write_text(room.model_dump_json(indent=2), encoding="utf-8")

    def get(self, room_id: str) -> RoomSpec | None:
        """Fetch room specification by room_id."""
        target = self._dir / f"{room_id}.json"
        if not target.is_file():
            return None
        try:
            return RoomSpec.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception as exc:
            _logger.debug("Failed decoding room file %s: %s", target, exc)
            return None

    def list_rooms(self) -> tuple[RoomSpec, ...]:
        """List all persisted rooms."""
        rooms: list[RoomSpec] = []
        for file in sorted(self._dir.glob("*.json")):
            try:
                rooms.append(RoomSpec.model_validate_json(file.read_text(encoding="utf-8")))
            except Exception as exc:
                _logger.debug("Failed reading room file %s: %s", file, exc)
                continue
        return tuple(rooms)

    def delete(self, room_id: str) -> bool:
        """Delete room specification. Returns True if deleted, False if not found."""
        target = self._dir / f"{room_id}.json"
        if target.is_file():
            target.unlink()
            return True
        return False


class RoomMessageRouter:
    """Evaluates incoming room messages against the RoomSpec's routing policy using dynamic discovery."""

    def __init__(
        self,
        room: RoomSpec,
        member_names: Mapping[str, str] | None = None,
        role_library: Any | None = None,
    ) -> None:
        self._room = room
        self._member_names = dict(member_names) if member_names else {}
        self._role_library = role_library

    def route_message(self, message: str) -> tuple[str, ...]:
        """Determine recipient agent/peer IDs based on message content and routing policy."""
        mentioned: list[str] = []

        # 检查各成员的显式 @ 标识与别名
        for peer_id in self._room.member_peer_ids:
            if f"@{peer_id}" in message:
                if peer_id not in mentioned:
                    mentioned.append(peer_id)
                continue

            name = self._resolve_name(peer_id)
            if name and f"@{name}" in message and peer_id not in mentioned:
                mentioned.append(peer_id)

        # 检查协调者 @ 标识
        coord_id = self._room.coordinator_agent_id
        if (f"@{coord_id}" in message or "@协调者" in message) and (coord_id not in mentioned):
            mentioned.append(coord_id)

        # 策略 1: coordinator_first（默认协调者收敛）
        if self._room.routing_policy == "coordinator_first":
            if mentioned:
                return tuple(mentioned)
            return (self._room.coordinator_agent_id,)

        # 策略 2: mention_only（纯点名触发）
        if self._room.routing_policy == "mention_only":
            return tuple(mentioned)

        return (self._room.coordinator_agent_id,)

    def _resolve_name(self, peer_id: str) -> str:
        """Dynamically resolve display name for peer_id."""
        if peer_id in self._member_names:
            return self._member_names[peer_id]

        # 1. 尝试从 AssistantHome/meta.json 动态读取
        try:
            home_dir = get_lca_home() / "assistants" / peer_id
            meta_file = home_dir / "meta.json"
            if meta_file.is_file():
                meta_json = json.loads(meta_file.read_text(encoding="utf-8"))
                name = meta_json.get("name")
                if name:
                    self._member_names[peer_id] = str(name)
                    return str(name)
        except Exception as exc:
            _logger.debug("Error reading assistant meta for %s: %s", peer_id, exc)

        # 2. 尝试从 RoleLibrary 动态反解
        lib = self._get_role_library()
        if lib is not None:
            candidate_keys = [
                peer_id,
                peer_id.replace("_", "/"),
            ]
            if peer_id.startswith("arch_"):
                candidate_keys.append(f"architecture/{peer_id.removeprefix('arch_')}")
            for cand in candidate_keys:
                try:
                    card = lib.get(cand)
                    self._member_names[peer_id] = card.title
                    return card.title
                except Exception as exc:
                    _logger.debug("Candidate %s not in role library: %s", cand, exc)
                    continue

        return ""

    def _get_role_library(self) -> Any | None:
        if self._role_library is not None:
            return self._role_library
        try:
            from lca.agent.role_library import FileRoleLibrary

            self._role_library = FileRoleLibrary()
            return self._role_library
        except Exception:
            return None


class RoomMessageStore(Protocol):
    """Protocol for append-only room transcript persistence."""

    def append(self, message: RoomMessage) -> None: ...
    def list_messages(self, room_id: str) -> tuple[RoomMessage, ...]: ...
    def get(self, room_id: str, message_id: str) -> RoomMessage | None: ...


class JsonRoomMessageStore(RoomMessageStore):
    """File-backed RoomMessageStore persisting ``~/.lca/rooms/<room_id>/messages.jsonl``.

    Appends are idempotent per ``message_id``; ``list_messages`` returns
    messages in creation order (stable by ``created_at_ms``).
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        root = base_dir or get_lca_home()
        self._rooms_dir = root / "rooms"
        self._rooms_dir.mkdir(parents=True, exist_ok=True)
        self._seen: dict[str, set[str]] = {}

    def _path(self, room_id: str) -> Path:
        return self._rooms_dir / room_id / "messages.jsonl"

    def _load_seen(self, room_id: str) -> set[str]:
        seen = self._seen.get(room_id)
        if seen is not None:
            return seen
        seen = set()
        path = self._path(room_id)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = RoomMessage.model_validate_json(line)
                    seen.add(msg.message_id)
                except Exception as exc:
                    _logger.debug("Failed decoding room message line in %s: %s", path, exc)
        self._seen[room_id] = seen
        return seen

    def append(self, message: RoomMessage) -> None:
        """Append one message. Idempotent: a known ``message_id`` is skipped."""
        seen = self._load_seen(message.room_id)
        if message.message_id in seen:
            return
        path = self._path(message.room_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(message.model_dump_json() + "\n")
        seen.add(message.message_id)

    def list_messages(self, room_id: str) -> tuple[RoomMessage, ...]:
        """Return all messages for a room in creation order."""
        path = self._path(room_id)
        if not path.is_file():
            return ()
        messages: list[RoomMessage] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(RoomMessage.model_validate_json(line))
            except Exception as exc:
                _logger.debug("Failed decoding room message line in %s: %s", path, exc)
        messages.sort(key=lambda msg: (msg.created_at_ms, msg.message_id))
        return tuple(messages)

    def get(self, room_id: str, message_id: str) -> RoomMessage | None:
        """Fetch one message by id, or ``None`` when absent."""
        for msg in self.list_messages(room_id):
            if msg.message_id == message_id:
                return msg
        return None


__all__ = [
    "JsonRoomMessageStore",
    "JsonRoomRepository",
    "RoomMessageRouter",
    "RoomMessageStore",
    "RoomRepository",
]
