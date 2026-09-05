"""Session spine→SSOT hook wiring tests."""

from __future__ import annotations

from lca.infrastructure.observability.loop_cursor._spine_port import get_session_append_hook
from lca.plugins.session.runtime.bind import (
    bind_run_event_session_from_store,
    unbind_run_event_session,
)
from lca.plugins.session.runtime.store import SessionStore


def test_bind_run_event_session_installs_spine_append_hook() -> None:
    store = SessionStore()
    assert get_session_append_hook() is None
    bound = bind_run_event_session_from_store(store, "run_hook_1")
    try:
        assert get_session_append_hook() is not None
        assert store.get("run_hook_1") is bound.bridge.inner
    finally:
        unbind_run_event_session(bound)
    assert get_session_append_hook() is None
