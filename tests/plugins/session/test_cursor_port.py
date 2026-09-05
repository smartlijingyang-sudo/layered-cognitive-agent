"""SessionWritePortAdapter — loop_cursor WritePort → Session.append(ADR-0186).

钉死三件事:
- 6 字段 WritePort append 翻译成 session event(``type`` = execution_point,
  ``data`` = payload 并入 ``incarnation``)。
- 返回传入的 ``seq``(WritePort 语义,SSOT seq 不因端口漂移)。
- 无 bound session 时 fail-loud(构造期抛错,不在 adapter 内回退 spine)。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.session.runtime.cursor_port import SessionWritePortAdapter
from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore


def _append_once(
    adapter: SessionWritePortAdapter,
    *,
    execution_point: str = "phase.think.fold",
    payload: dict[str, Any] | None = None,
    seq: int = 7,
    incarnation: int = 3,
    phase: str | None = "think",
) -> int:
    return adapter.append(
        execution_point=execution_point,
        payload=payload if payload is not None else {"phase": "think", "objective": "o"},
        run_id="run_1",
        seq=seq,
        incarnation=incarnation,
        phase=phase,
    )


def test_append_translates_to_session_event_with_ep_type_and_incarnation() -> None:
    session = Session("run_port_1")
    adapter = SessionWritePortAdapter(session)

    returned_seq = _append_once(adapter, incarnation=5, seq=11)

    assert returned_seq == 11
    assert session.seq == 1
    event = session.event_at(0)
    assert event is not None
    # type = execution_point(EP 名);data = payload + incarnation
    assert event.type == "phase.think.fold"
    assert event.data == {"phase": "think", "objective": "o", "incarnation": 5}


def test_append_accepts_run_session_bridge() -> None:
    """构造接受 run bind 产出的 bridge(读 ``.inner``),与裸 Session 等价。"""
    from lca.plugins.session.runtime.bind import (
        bind_run_event_session_from_store,
        unbind_run_event_session,
    )

    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "run_port_2")
    try:
        adapter = SessionWritePortAdapter(bound.bridge)
        _append_once(adapter, execution_point="llm.request.header", incarnation=1)
        inner = bound.bridge.inner
        event = inner.event_at(0)
        assert event is not None
        assert event.type == "llm.request.header"
        assert event.data["incarnation"] == 1
    finally:
        unbind_run_event_session(bound)


def test_append_preserves_existing_payload_keys_and_overrides_incarnation() -> None:
    session = Session("run_port_3")
    adapter = SessionWritePortAdapter(session)
    # payload 自带 incarnation 键时,以 WritePort 入参为准(与合并语义一致)。
    _append_once(
        adapter,
        payload={"phase": "act", "incarnation": 99, "extra": "x"},
        incarnation=2,
    )
    event = session.event_at(0)
    assert event is not None
    assert event.data == {"phase": "act", "extra": "x", "incarnation": 2}


def test_append_rejects_non_json_serializable_payload() -> None:
    """Session.append 校验失败上抛(fail-loud),日志不变。"""
    session = Session("run_port_4")
    adapter = SessionWritePortAdapter(session)
    with pytest.raises(TypeError):
        _append_once(adapter, payload={"bad": object()})
    assert session.seq == 0


def test_construct_without_bound_session_fails_loud() -> None:
    with pytest.raises(ValueError):
        SessionWritePortAdapter(None)
    # 无 ``.inner`` 的任意对象也解析不到 Session → fail-loud
    with pytest.raises(ValueError):
        SessionWritePortAdapter(object())
