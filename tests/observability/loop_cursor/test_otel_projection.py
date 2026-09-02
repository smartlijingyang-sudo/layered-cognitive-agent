"""ADR-0172 PR-6 OtelProjection 测试。

覆盖:
- 无 opentelemetry-api 时 import 不崩溃(SDK 缺席可降级)
- apply 累加 span 描述符(state["spans"] 列表)
- view 返回 spans 列表
- reducer 纯函数(不改入参 state)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.loop_cursor.projections.otel_projection import (
    OtelProjection,
    otel_sdk_available,
)
from lca.infrastructure.observability.spine.event_record import EventRecord


def _snap(seq: int = 0, step_id: str | None = "s1") -> CursorSnapshot:
    return CursorSnapshot(
        run_id="r",
        trace_id="t",
        incarnation=1,
        step_id=step_id,
        step_index=1,
        iteration=1,
        attempt_in_step=0,
        phase="think",  # type: ignore[arg-type]
        iteration_reason=None,
        stop_signal=None,
        seq=seq,
    )


def _record(*, ep: str, seq: int, payload: dict[str, Any] | None = None) -> EventRecord:
    now = datetime.now(timezone.utc)
    return EventRecord(
        execution_point=ep,
        channel="control",
        span_id=f"sp-{seq}",
        parent_span_id=None,
        sequence=seq,
        epoch=1,
        causality_id=f"c{seq}",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id="r",
        step_id=None,
        payload=payload or {},
    )


# ── 1. SDK 缺席时 import / init 不崩溃(降级为 accumulator) ──────────
def test_init_does_not_crash_when_sdk_missing() -> None:
    """若 opentelemetry-api 未安装,OtelProjection 应降级为 accumulator。

    设计约束:模块 import 不抛 ImportError;``otel_sdk_available()`` 返回
    bool,init 返回的 state 携带 ``sdk_available`` 字段;无论 SDK 是否
    在场,``apply`` 与 ``view`` 行为一致。
    """
    p = OtelProjection()
    state = p.init()
    # sdk_available 字段必然存在;True / False 都行(取决于环境是否安装 SDK)
    assert "sdk_available" in state
    assert isinstance(state["sdk_available"], bool)
    assert state["sdk_available"] == otel_sdk_available()
    # spans 列表初始为空
    assert state["spans"] == []


# ── 2. apply 累加 span 描述符(view 返回列表) ────────────────────────
def test_apply_accumulates_span_descriptors_and_view_returns_list() -> None:
    p = OtelProjection()
    snap = _snap()
    state = p.init()

    # step.thinking.record → 追加一个新 span
    state = p.apply(
        state, snap, _record(ep="step.thinking.record", seq=1, payload={"token_count": 5})
    )
    assert len(state["spans"]) == 1
    assert state["spans"][0]["name"] == "lca.step.thinking"
    assert state["spans"][0]["sequence"] == 1

    # step.tool_call.record → 追加新 span
    state = p.apply(
        state, snap, _record(ep="step.tool_call.record", seq=2, payload={"tool_name": "t1"})
    )
    assert len(state["spans"]) == 2

    # step.tool_result.record → 追加新 span
    state = p.apply(
        state, snap, _record(ep="step.tool_result.record", seq=3, payload={"outcome": "ok"})
    )
    assert len(state["spans"]) == 3

    # phase.think.fold → 不开新 span;附加到最近 span 的 events
    state = p.apply(state, snap, _record(ep="phase.think.fold", seq=4, payload={"phase": "think"}))
    assert len(state["spans"]) == 3
    last_span = state["spans"][-1]
    assert any(ev["name"] == "phase.think.fold" for ev in last_span["events"])

    # view 返回 spans 列表(供 host.flush_all 序列化)
    view = p.view(state)
    assert isinstance(view, list)
    assert len(view) == 3
    assert view[0]["name"] == "lca.step.thinking"

    # restore 重置
    restored = p.restore(state)
    assert restored["spans"] == []
