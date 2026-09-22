"""Collaboration Room specification repository and message routing (ADR-0250).

Provides RoomSpec persistence (JsonRoomRepository) and room-level message routing policies
(coordinator_first vs mention_only).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from lca.contracts.models.collaboration.peer import RoomSpec
from lca.infrastructure.path.locator import get_lca_home

_logger = logging.getLogger(__name__)

_PEER_NICKNAME_MAP: dict[str, str] = {
    "观澜": "arch_guanlan",
    "衡岳": "arch_hengyue",
    "镜川": "arch_jingchuan",
}


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
    """Evaluates incoming room messages against the RoomSpec's routing policy."""

    def __init__(self, room: RoomSpec) -> None:
        self._room = room

    def route_message(self, message: str) -> tuple[str, ...]:
        """Determine recipient agent/peer IDs based on message content and routing policy."""
        mentioned: list[str] = []

        # 检查显式 @ 标识与别名
        for name, peer_id in _PEER_NICKNAME_MAP.items():
            if (f"@{name}" in message or f"@{peer_id}" in message) and (
                peer_id not in mentioned and peer_id in self._room.member_peer_ids
            ):
                mentioned.append(peer_id)

        if (f"@{self._room.coordinator_agent_id}" in message or "@协调者" in message) and (
            self._room.coordinator_agent_id not in mentioned
        ):
            mentioned.append(self._room.coordinator_agent_id)

        # 策略 1: coordinator_first（默认协调者收敛）
        if self._room.routing_policy == "coordinator_first":
            if mentioned:
                return tuple(mentioned)
            return (self._room.coordinator_agent_id,)

        # 策略 2: mention_only（纯点名触发）
        if self._room.routing_policy == "mention_only":
            return tuple(mentioned)

        return (self._room.coordinator_agent_id,)
