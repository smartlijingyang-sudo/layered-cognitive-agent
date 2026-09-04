"""Session 契约测试 —— ADR-0185 PR-3a。

验证 Session 契约(frozen dataclass + Protocol)的结构正确性;
不测试 Session 实现类(PR-3b)。
"""

from __future__ import annotations

from typing import Any

from lca_kernel.events.session import (
    SessionEvent,
    SessionHeader,
    SessionObserver,
    SessionProtocol,
    SessionReentryError,
)

# ── SessionHeader ────────────────────────────────────────────────────────


def test_session_header_frozen_and_fields() -> None:
    """SessionHeader frozen + 全字段可构造。"""
    h = SessionHeader(version=0, id="s-1", created_at=1000.0)
    assert h.version == 0
    assert h.id == "s-1"
    assert h.created_at == 1000.0
    assert h.is_seeded is False
    assert h.cwd is None
    assert h.parent_session is None
    assert h.origin is None
    assert h.delegation_depth == 0
    assert h.agent_preset is None


def test_session_header_frozen_rejects_mutation() -> None:
    """SessionHeader frozen: 原地改字段抛 FrozenInstanceError。"""
    h = SessionHeader(version=0, id="s-1", created_at=1000.0)
    import pytest

    with pytest.raises(AttributeError):
        h.id = "s-2"  # type: ignore[misc]


def test_session_header_all_optional_fields() -> None:
    """SessionHeader 可选字段全部可设。"""
    h = SessionHeader(
        version=0,
        id="s-2",
        created_at=2000.0,
        is_seeded=True,
        cwd="/home/test",
        parent_session="s-0",
        origin="subagent",
        delegation_depth=2,
        agent_preset="web-coder",
    )
    assert h.is_seeded is True
    assert h.cwd == "/home/test"
    assert h.parent_session == "s-0"
    assert h.origin == "subagent"
    assert h.delegation_depth == 2
    assert h.agent_preset == "web-coder"


# ── SessionEvent ─────────────────────────────────────────────────────────


def test_session_event_frozen_and_fields() -> None:
    """SessionEvent frozen + 字段正确。"""
    e = SessionEvent(seq=0, time=100.0, type="turn/start", data={"turn": 0})
    assert e.seq == 0
    assert e.time == 100.0
    assert e.type == "turn/start"
    assert e.data == {"turn": 0}
    assert e.ignorable is False


def test_session_event_ignorable_flag() -> None:
    """SessionEvent ignorable=True 可设。"""
    e = SessionEvent(seq=1, time=200.0, type="unknown/type", data={}, ignorable=True)
    assert e.ignorable is True


def test_session_event_frozen_rejects_mutation() -> None:
    """SessionEvent frozen: 原地改字段抛 FrozenInstanceError。"""
    e = SessionEvent(seq=0, time=100.0, type="step/start", data={})
    import pytest

    with pytest.raises(AttributeError):
        e.seq = 1  # type: ignore[misc]


# ── SessionReentryError ──────────────────────────────────────────────────


def test_session_reentry_error_is_runtime_error() -> None:
    """SessionReentryError 是 RuntimeError 子类。"""
    err = SessionReentryError("append reentered")
    assert isinstance(err, RuntimeError)
    assert "reentered" in str(err)


# ── SessionObserver Protocol ─────────────────────────────────────────────


def test_session_observer_protocol_structural() -> None:
    """SessionObserver 是 runtime_checkable Protocol;满足结构的类通过检查。"""

    class GoodObserver:
        def on_session_event(self, session: Any, event: Any) -> None:
            pass

    class BadObserver:
        pass

    assert isinstance(GoodObserver(), SessionObserver)
    assert not isinstance(BadObserver(), SessionObserver)


# ── SessionProtocol Protocol ─────────────────────────────────────────────


def test_session_protocol_structural() -> None:
    """SessionProtocol 是 runtime_checkable Protocol;满足结构的类通过检查。"""

    class MinimalSession:
        @property
        def id(self) -> str:
            return "s-1"

        @property
        def header(self) -> SessionHeader:
            return SessionHeader(version=0, id="s-1", created_at=0.0)

        @property
        def event_count(self) -> int:
            return 0

        def event_at(self, seq: int) -> SessionEvent | None:
            return None

        def snapshot_events(
            self, from_seq: int = 0, to_seq: int | None = None
        ) -> list[SessionEvent]:
            return []

        def append(self, type: str, data: dict[str, Any]) -> SessionEvent:
            return SessionEvent(seq=0, time=0.0, type=type, data=data)

        def request_header(self) -> Any | None:
            return None

        def step_tree(self) -> Any:
            from lca_kernel.events.fold import StepTree

            return StepTree()

    assert isinstance(MinimalSession(), SessionProtocol)
