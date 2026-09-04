"""Session 契约结构测试(对齐 PR-3c session.py)。"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.session import (
    SESSION_FORMAT_VERSION,
    SessionEvent,
    SessionHeader,
    SessionObserver,
    SessionProtocol,
    SessionReentryError,
)


def test_session_format_version_is_int() -> None:
    assert isinstance(SESSION_FORMAT_VERSION, int)
    assert SESSION_FORMAT_VERSION == 0


def test_session_header_frozen() -> None:
    h = SessionHeader(version=SESSION_FORMAT_VERSION, id="s1", created_at=1)
    with pytest.raises(Exception):
        h.id = "x"  # type: ignore[misc]
    assert h.version == SESSION_FORMAT_VERSION


def test_session_event_frozen() -> None:
    e = SessionEvent(type="test/x", seq=0, time=1, data={"a": 1})
    with pytest.raises(Exception):
        e.seq = 2  # type: ignore[misc]
    assert e.type == "test/x"


def test_session_reentry_error_is_runtime_error() -> None:
    assert issubclass(SessionReentryError, RuntimeError)


def test_session_observer_protocol_structural() -> None:
    class Obs:
        def __call__(self, session: Any, event: SessionEvent) -> None:
            return None

    assert isinstance(Obs(), SessionObserver)


def test_session_protocol_structural_via_runtime() -> None:
    from lca.plugins.session.runtime.session import Session

    s = Session(session_id="s-test")
    assert isinstance(s, SessionProtocol)
