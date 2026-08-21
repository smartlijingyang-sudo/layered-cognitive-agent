"""Session projection SPI (spec §2.2.6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProjectionSnapshot:
    as_of_seq: int
    values: dict[str, Any]


@dataclass(frozen=True)
class ProjectionChange:
    session_id: str
    key: str
    version: int
    seq: int
    value: Any


class ProjectionDefinition(Protocol):
    """Pure reducer: init → apply(event) → view."""

    key: str
    version: int

    def init(self) -> Any: ...

    def apply(self, state: Any, event: Any) -> Any: ...

    def view(self, state: Any) -> Any: ...


class ProjectionRegistry(Protocol):
    def register(self, definition: ProjectionDefinition) -> Any: ...

    def snapshot(self, session_id: str) -> ProjectionSnapshot: ...

    def subscribe_changes(self, listener: Callable[[ProjectionChange], None]) -> Any: ...
