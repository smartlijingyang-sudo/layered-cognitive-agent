"""ADR-0172 PR-6 MetricsProjection 测试。

覆盖:
- init 默认 MetricsState(全零)
- 累加 step.thinking.record / step.tool_call.record
- view 返回 dict(asdict)
- token_count 累加与缺省 0
- 不修改入参 state(纯 reducer)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.loop_cursor.projections.metrics_projection import (
    MetricsProjection,
    MetricsState,
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


# ── 1. init ──────────────────────────────────────────────────────────
def test_init_returns_zero_state() -> None:
    p = MetricsProjection()
    state = p.init()
    assert state == MetricsState()
    assert state.step_count == 0
    assert state.tool_call_count == 0
    assert state.total_tokens == 0


# ── 2. counters increment on spine events ────────────────────────────
def test_counters_increment_on_thinking_and_tool_events() -> None:
    p = MetricsProjection()
    snap = _snap()
    state = p.init()

    state = p.apply(
        state, snap, _record(ep="step.thinking.record", seq=1, payload={"token_count": 42})
    )
    state = p.apply(
        state, snap, _record(ep="step.thinking.record", seq=2, payload={"token_count": 8})
    )
    state = p.apply(
        state, snap, _record(ep="step.tool_call.record", seq=3, payload={"tool_name": "t1"})
    )
    state = p.apply(
        state, snap, _record(ep="step.tool_result.record", seq=4, payload={"outcome": "ok"})
    )
    # 无关 EP 不影响
    state = p.apply(state, snap, _record(ep="phase.think.fold", seq=5))

    assert state.step_count == 2
    assert state.tool_call_count == 2
    assert state.total_tokens == 50


# ── 3. view returns asdict(state) ────────────────────────────────────
def test_view_returns_serializable_dict() -> None:
    p = MetricsProjection()
    state = MetricsState(step_count=3, tool_call_count=1, total_tokens=99)
    view = p.view(state)
    assert view == {"step_count": 3, "tool_call_count": 1, "total_tokens": 99}
    # 可 JSON 序列化(dict,value 全部 int)
    import json

    json.dumps(view)


# ── 4. apply is pure(不改入参 state) ─────────────────────────────────
def test_apply_does_not_mutate_input_state() -> None:
    p = MetricsProjection()
    snap = _snap()
    state = MetricsState(step_count=1, tool_call_count=1, total_tokens=10)
    frozen_like_before = (state.step_count, state.tool_call_count, state.total_tokens)

    new_state = p.apply(
        state, snap, _record(ep="step.thinking.record", seq=1, payload={"token_count": 5})
    )

    assert (state.step_count, state.tool_call_count, state.total_tokens) == frozen_like_before
    assert new_state is not state
    assert new_state.step_count == 2
    assert new_state.total_tokens == 15


# ── 5. restore 重置为 seed ──────────────────────────────────────────
def test_restore_resets_state() -> None:
    p = MetricsProjection()
    state = MetricsState(step_count=5, tool_call_count=3, total_tokens=200)
    restored = p.restore(state)
    assert restored == MetricsState()


# ── 6. payload 缺 token_count 时按 0 累加 ───────────────────────────
def test_missing_token_count_treated_as_zero() -> None:
    p = MetricsProjection()
    snap = _snap()
    state = p.init()
    state = p.apply(
        state, snap, _record(ep="step.thinking.record", seq=1, payload={"content_digest": "d"})
    )
    assert state.step_count == 1
    assert state.total_tokens == 0
