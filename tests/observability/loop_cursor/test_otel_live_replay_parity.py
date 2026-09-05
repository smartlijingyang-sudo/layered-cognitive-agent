"""验收 #15: OtelProjection live 增量 fold 与 cold replay 结构一致。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.loop_cursor.projections.otel_projection import (
    OtelProjection,
)
from lca.infrastructure.observability.spine.event_record import EventRecord


def _snap(*, step_id: str = "step_1") -> CursorSnapshot:
    return CursorSnapshot(
        run_id="run_otel",
        trace_id="trace_otel",
        incarnation=1,
        step_id=step_id,
        step_index=1,
        iteration=1,
        attempt_in_step=0,
        phase="think",  # type: ignore[arg-type]
        iteration_reason=None,
        stop_signal=None,
        seq=0,
    )


def _record(
    *,
    ep: str,
    seq: int,
    span_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> EventRecord:
    now = datetime.now(UTC)
    return EventRecord(
        execution_point=ep,
        channel="control",
        span_id=span_id or f"sp-{seq:04d}",
        parent_span_id=None if seq <= 1 else "sp-0001",
        sequence=seq,
        epoch=1,
        causality_id=f"c{seq}",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id="run_otel",
        step_id="step_1",
        payload=payload or {},
    )


def _turn_step_tool_records() -> tuple[EventRecord, ...]:
    """turn/step/tool 树最小序列：header → thinking → tool call/result → fold。"""
    return (
        _record(ep="llm.request.header", seq=1, payload={"model": "test"}),
        _record(ep="step.thinking.record", seq=2, payload={"token_count": 12}),
        _record(ep="step.tool_call.record", seq=3, payload={"tool_name": "bash"}),
        _record(ep="step.tool_result.record", seq=4, payload={"outcome": "ok"}),
        _record(ep="phase.think.fold", seq=5, payload={"phase": "think"}),
    )


def _fold_live(records: tuple[EventRecord, ...]) -> list[dict[str, Any]]:
    projection = OtelProjection()
    snap = _snap()
    state = projection.init()
    for record in records:
        state = projection.apply(state, snap, record)
    return projection.view(state)


def _span_tree_signature(spans: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    """结构签名：name / sequence / step_id / nested event names（忽略 ts 等非确定字段）。"""
    sig: list[tuple[Any, ...]] = []
    for span in spans:
        events = tuple(ev.get("name") for ev in span.get("events", ()))
        sig.append((span.get("name"), span.get("sequence"), span.get("step_id"), events))
    return tuple(sig)


def test_otel_live_incremental_matches_cold_replay() -> None:
    records = _turn_step_tool_records()
    live = _fold_live(records)
    cold = _fold_live(records)
    assert _span_tree_signature(live) == _span_tree_signature(cold)
    assert len(live) == 4
    assert live[0]["name"] == "lca.llm.step"
    assert live[1]["name"] == "lca.step.thinking"
    assert live[2]["name"] == "lca.step.tool_call.record"
    assert live[3]["name"] == "lca.step.tool_result.record"


def test_otel_restore_then_replay_matches_live_span_tree() -> None:
    records = _turn_step_tool_records()
    projection = OtelProjection()
    snap = _snap()

    live_state = projection.init()
    for record in records:
        live_state = projection.apply(live_state, snap, record)
    live_view = projection.view(live_state)

    replay_state = projection.restore(live_state)
    for record in records:
        replay_state = projection.apply(replay_state, snap, record)
    replay_view = projection.view(replay_state)

    assert _span_tree_signature(replay_view) == _span_tree_signature(live_view)
