"""Regression lock: ``Session bindings.resolve_session_reader`` must observe
live updates to ``_session_publish._ACTIVE_SESSION``.

The publish Session is a process-wide module global. When ``set_publish_session``
reassigns it, every consumer that reads via the module attribute sees the
new value. A consumer that captured the value at import time via
``from lca.plugins.events.publishers._session_publish import _ACTIVE_SESSION``
keeps the stale initial ``None`` and never sees updates.

Before the fix, ``record(AgentRunStarted)`` raised
``requires a bound Session`` at the start of every backend run because
``infrastructure.session.bindings`` had stale-captured the ``None`` value at
import time. This test pins the live-read invariant.
"""

from __future__ import annotations

from lca.infrastructure.session import bindings
from lca.plugins.events.publishers import _session_publish


def test_resolve_session_reader_sees_set_publish_session() -> None:
    """``set_publish_session(s)`` then ``bindings._active_publish_session()``
    returns ``s``, not the import-time-captured ``None``.
    """
    sentinel = object()
    try:
        _session_publish.set_publish_session(sentinel)
        assert bindings._active_publish_session() is sentinel
        assert _session_publish._ACTIVE_SESSION is sentinel
    finally:
        _session_publish.reset_publish_session(None)


def test_resolve_session_reader_returns_none_after_reset() -> None:
    """``reset_publish_session`` is observed immediately by live readers."""
    _session_publish.set_publish_session(object())
    _session_publish.reset_publish_session(None)
    assert bindings._active_publish_session() is None
    assert bindings.resolve_session_reader() is None


def test_active_publish_session_does_not_capture_stale_value() -> None:
    """A second ``set_publish_session`` overrides a previous binding even
    though ``bindings`` was imported before either call.
    """
    first = object()
    second = object()
    try:
        _session_publish.set_publish_session(first)
        assert bindings._active_publish_session() is first
        _session_publish.set_publish_session(second)
        assert bindings._active_publish_session() is second
        assert bindings._active_publish_session() is not first
    finally:
        _session_publish.reset_publish_session(None)
