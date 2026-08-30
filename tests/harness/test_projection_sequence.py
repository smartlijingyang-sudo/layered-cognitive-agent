from __future__ import annotations

import pytest

from lca.contracts.harness.tasks.session import SessionEvent
from lca.harness.projection.registry import InMemoryProjectionRegistry


class _CounterProjection:
    key = "counter"
    version = 1

    def init(self) -> int:
        return 0

    def apply(self, state: int, event: SessionEvent) -> int:
        return state + 1

    def view(self, state: int) -> int:
        return state


def _event(seq: int) -> SessionEvent:
    return SessionEvent(type="test", seq=seq, time=seq, data={}, session_id="session-1")


def test_projection_registry_rejects_duplicate_or_out_of_order_events() -> None:
    registry = InMemoryProjectionRegistry()
    registry.register(_CounterProjection())  # type: ignore[arg-type]
    registry.on_event(_event(2))
    assert registry.snapshot("session-1").values == {"counter": 1}

    with pytest.raises(ValueError, match="sequence must increase"):
        registry.on_event(_event(2))
    with pytest.raises(ValueError, match="sequence must increase"):
        registry.on_event(_event(1))

    assert registry.snapshot("session-1").values == {"counter": 1}
