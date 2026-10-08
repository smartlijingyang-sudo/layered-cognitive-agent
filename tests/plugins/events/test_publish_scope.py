"""RA-044: publish_scope seam — bind/unbind pairing and None-safety."""

from __future__ import annotations

from typing import Any

from lca.plugins.events import _session_observe
from lca.plugins.events.publish_scope import bind_event_bridge, unbind_event_bridge
from lca.plugins.events.publishers import _session_publish


class _FakeBridge:
    """Minimal event bridge: satisfies set_session's observe requirement."""

    def __init__(self) -> None:
        self.observed: list[tuple[type, Any]] = []

    def observe(self, plugin: type, callback: Any) -> None:
        self.observed.append((plugin, callback))


def test_bind_and_unbind_roundtrip() -> None:
    bridge = _FakeBridge()
    token = bind_event_bridge(bridge)
    assert token is not None
    assert _session_publish.get_active_session() is bridge
    assert _session_observe.current_session() is bridge
    unbind_event_bridge(token)
    assert _session_publish.get_active_session() is None
    assert _session_observe.current_session() is None


def test_none_bridge_is_noop() -> None:
    assert bind_event_bridge(None) is None
    # A None bind must not disturb an already-bound session.
    bridge = _FakeBridge()
    token = bind_event_bridge(bridge)
    try:
        assert bind_event_bridge(None) is None
        assert _session_publish.get_active_session() is bridge
        assert _session_observe.current_session() is bridge
    finally:
        unbind_event_bridge(token)


def test_unbind_none_is_noop() -> None:
    unbind_event_bridge(None)  # must not raise
    assert _session_publish.get_active_session() is None
