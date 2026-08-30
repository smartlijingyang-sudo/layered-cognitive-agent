"""One journal subscription drives every registered reducer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.harness.state.projection import (
    ProjectionChange,
    ProjectionDefinition,
    ProjectionSnapshot,
    SessionProjectionRegistry,
)
from lca.contracts.harness.tasks.session import SessionEvent


class InMemoryProjectionRegistry(SessionProjectionRegistry):
    """Per-session fold of registered projections."""

    def __init__(self) -> None:
        self._definitions: dict[str, ProjectionDefinition] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._seq: dict[str, int] = {}
        self._listeners: list[Callable[[ProjectionChange], None]] = []

    def register(self, definition: ProjectionDefinition) -> None:
        self._definitions[definition.key] = definition

    def bind_session(self, session_id: str) -> None:
        self._states[session_id] = {
            key: definition.init() for key, definition in self._definitions.items()
        }
        self._seq[session_id] = -1

    def on_event(self, event: SessionEvent) -> None:
        session_id = event.session_id
        if session_id not in self._states:
            self.bind_session(session_id)
        current_seq = self._seq[session_id]
        if event.seq <= current_seq:
            raise ValueError(
                f"projection event sequence must increase: {event.seq} <= {current_seq}"
            )
        self._seq[session_id] = event.seq
        for key, definition in self._definitions.items():
            before = self._states[session_id][key]
            after = definition.apply(before, event)
            self._states[session_id][key] = after
            change = ProjectionChange(
                session_id=session_id,
                key=key,
                version=definition.version,
                seq=event.seq,
                value=definition.view(after),
            )
            for listener in self._listeners:
                listener(change)

    def snapshot(self, session_id: str) -> ProjectionSnapshot:
        states = self._states.get(session_id)
        if states is None:
            return ProjectionSnapshot(as_of_seq=-1, values={})
        values = {key: self._definitions[key].view(state) for key, state in states.items()}
        return ProjectionSnapshot(as_of_seq=self._seq.get(session_id, -1), values=values)

    def subscribe_changes(self, listener: Callable[[ProjectionChange], None]) -> None:
        self._listeners.append(listener)

    def replay(self, session_id: str, events: list[SessionEvent]) -> None:
        self.bind_session(session_id)
        for event in events:
            self.on_event(event)
