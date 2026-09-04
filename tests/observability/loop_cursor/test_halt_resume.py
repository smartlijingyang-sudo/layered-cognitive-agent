"""ADR-0173 PR-5 halt-resume 协议测试。

覆盖:
- halt 锁住 record_* / advance 但不 close(cursor 实例保留);
- resume_cursor 派生**新**实例(I-RESUME-1),不复用 halted cursor;
- iteration_reason close-set("checkpoint_resume" / "user_replay" / "subagent_resume");
- incarnation_seq 在 resume 时保留(不递增;resume ≠ fork)。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import CursorError
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.contracts.observability.resume import ResumeSpec
from lca.infrastructure.observability.loop_cursor import (
    InMemoryLoopCursor,
    StdLoopCursor,
)

# ── shared fixtures ──────────────────────────────────────────────


@dataclass
class _StubSpine:
    records: list[dict] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict,
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {
                "execution_point": execution_point,
                "payload": payload,
                "run_id": run_id,
                "seq": seq,
                "incarnation": incarnation,
                "phase": phase,
            }
        )
        return seq


def _make_std_cursor(seq: int = 3) -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r-halt",
        trace_id="t-halt",
        incarnation=Incarnation(
            run_id="r-halt",
            plan_ref="plan-A",
            incarnation_seq=seq,
        ),
    )
    return cursor, spine


def _make_inmem(seq: int = 3) -> InMemoryLoopCursor:
    return InMemoryLoopCursor(
        run_id="r-halt",
        trace_id="t-halt",
        incarnation=Incarnation(
            run_id="r-halt",
            plan_ref="plan-A",
            incarnation_seq=seq,
        ),
    )


# ── 1. halt 锁住 record_* 但 cursor 实例未 close ──────────────────


def test_halt_locks_record_calls_std() -> None:
    """halt 后 record_* 抛 CursorError;但 advance('think') 也抛(锁住所有业务面)。"""
    c, _ = _make_std_cursor()
    c.advance("think")
    c.halt("loop_guard")
    with pytest.raises(CursorError):
        c.record_thinking(
            ThinkingRecord(
                content_digest="x",
                content_path=None,
                token_count=1,
                thinking_kind="reasoning",
            )
        )
    with pytest.raises(CursorError):
        c.record_tool_call(
            ToolCallRecord(
                tool_name="t",
                args_digest="x",
                args_payload_path=None,
                call_seq=1,
            )
        )
    with pytest.raises(CursorError):
        c.record_tool_result(
            ToolResultRecord(
                tool_name="t",
                result_digest="x",
                result_path=None,
                outcome="ok",
            )
        )
    with pytest.raises(CursorError):
        c.record_request_header(
            RequestHeader(
                step_id="s",
                incarnation=3,
                reason="initial",
                model="m",
                tools_digest="d2",
                tools_path="p2",
                messages_digest="d3",
                messages_path="p3",
                manifest_digest="d4",
                manifest_path="p4",
            )
        )
    with pytest.raises(CursorError):
        c.advance("act")


def test_halt_locks_record_calls_in_memory() -> None:
    c = _make_inmem()
    c.advance("think")
    c.halt("loop_guard")
    with pytest.raises(CursorError):
        c.record_thinking(None)  # type: ignore[arg-type]
    with pytest.raises(CursorError):
        c.advance("act")


# ── 2. halt 不关闭 state machine(快照仍可读 / halted=True) ───────


def test_halt_does_not_close_state_machine_std() -> None:
    """halt 后 cursor.snapshot 仍可读;halt 字段=True,closed 字段=False。"""
    c, spine = _make_std_cursor()
    c.advance("perceive")
    c.halt("loop_guard")
    snap = c.snapshot
    assert snap.stop_signal == "loop_guard"
    assert snap.phase == "perceive"
    # state 内部:halted=True,closed=False
    assert c._state.halted is True
    assert c._state.closed is False
    # halt 仍发 writable.iteration.halt EP(writable.iteration.closing 不应出现)
    last_ep = spine.records[-1]["execution_point"]
    assert last_ep == "writable.iteration.halt"
    assert all(r["execution_point"] != "writable.iteration.closing" for r in spine.records)


def test_halt_does_not_close_state_machine_in_memory() -> None:
    c = _make_inmem()
    c.advance("perceive")
    c.halt("user_stop")
    assert c.snapshot.stop_signal == "user_stop"
    assert c._state.halted is True
    assert c._state.closed is False


def test_close_after_halt_still_raises() -> None:
    """halt 后再 close 应正常工作;但 close 之后 record_* 抛(双状态机兼容)。"""
    c, _ = _make_std_cursor()
    c.advance("think")
    c.halt("loop_guard")
    c.close("user_stop")
    assert c._state.halted is True
    assert c._state.closed is True
    with pytest.raises(CursorError):
        c.advance("perceive")


# ── 3. resume_cursor 重建状态(派生新实例) ────────────────────────


def test_resume_cursor_rebuilds_state_std() -> None:
    """halt 旧 cursor + resume_cursor(spec) → 新实例,字段正确注入。"""
    old, spine = _make_std_cursor(seq=4)
    old.advance("perceive")
    old.halt("loop_guard")
    # 旧 cursor 已被 halt,record_* 抛
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=4,
        iteration=2,
        step_index=3,
        phase="think",
        iteration_reason="checkpoint_resume",
    )
    new = StdLoopCursor.resume_cursor(spine=spine, spec=spec, trace_id="t-halt-2")
    # I-RESUME-1:新 cursor != 旧 cursor
    assert new is not old
    # identity 保留
    assert new.snapshot.run_id == "r-halt"
    assert new.snapshot.incarnation == 4
    # spec 字段注入
    assert new.snapshot.phase == "think"
    assert new.snapshot.iteration == 2
    assert new.snapshot.step_index == 3
    assert new.snapshot.iteration_reason == "checkpoint_resume"
    # 新 cursor 默认 closed=False, halted=False(可继续 advance)
    assert new._state.halted is False
    assert new._state.closed is False


def test_resume_cursor_rebuilds_state_in_memory() -> None:
    old = _make_inmem(seq=4)
    old.advance("perceive")
    old.halt("loop_guard")
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=4,
        iteration=2,
        step_index=3,
        phase="think",
        iteration_reason="user_replay",
    )
    new = InMemoryLoopCursor.resume_cursor(spec=spec, trace_id="t-halt-2")
    assert new is not old
    assert new.snapshot.run_id == "r-halt"
    assert new.snapshot.incarnation == 4
    assert new.snapshot.phase == "think"
    assert new.snapshot.iteration == 2
    assert new.snapshot.step_index == 3
    assert new.snapshot.iteration_reason == "user_replay"


# ── 4. iteration_reason close-set ────────────────────────────────


def test_resume_with_checkpoint_resume_iteration_reason() -> None:
    c, spine = _make_std_cursor()
    c.halt("loop_guard")
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
        iteration_reason="checkpoint_resume",
    )
    new = StdLoopCursor.resume_cursor(spine=spine, spec=spec, trace_id="t-halt-2")
    assert new.snapshot.iteration_reason == "checkpoint_resume"


def test_resume_with_user_replay_iteration_reason() -> None:
    c, spine = _make_std_cursor()
    c.halt("user_stop")
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
        iteration_reason="user_replay",
    )
    new = StdLoopCursor.resume_cursor(spine=spine, spec=spec, trace_id="t-halt-2")
    assert new.snapshot.iteration_reason == "user_replay"


def test_resume_with_subagent_resume_iteration_reason() -> None:
    c, spine = _make_std_cursor()
    c.halt("loop_guard")
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
        iteration_reason="subagent_resume",
    )
    new = StdLoopCursor.resume_cursor(spine=spine, spec=spec, trace_id="t-halt-2")
    assert new.snapshot.iteration_reason == "subagent_resume"


# ── 5. incarnation_seq 在 resume 时保留 ──────────────────────────


def test_resume_preserves_incarnation_seq() -> None:
    """resume ≠ fork(ADR-0171):incarnation_seq 不递增。"""
    c, spine = _make_std_cursor(seq=7)
    c.halt("loop_guard")
    spec = ResumeSpec(
        run_id="r-halt",
        plan_ref="plan-A",
        incarnation_seq=7,  # 与旧 cursor 同
        iteration=1,
        step_index=2,
        phase="act",
        iteration_reason="checkpoint_resume",
    )
    new = StdLoopCursor.resume_cursor(spine=spine, spec=spec, trace_id="t-halt-2")
    # resume 保留 incarnation_seq(≠ fork 的 += 1)
    assert new.snapshot.incarnation == 7
    assert new._state.incarnation.incarnation_seq == 7
    # 与 fork 形成对比:fork 必须 seq += 1
    child = c.fork("child_agent")
    assert child.snapshot.incarnation == 8


# ── 6. ResumeSpec frozen=True 校验 ───────────────────────────────


def test_resume_spec_is_frozen() -> None:
    spec = ResumeSpec(
        run_id="r",
        plan_ref="p",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
    )
    with pytest.raises(FrozenInstanceError):
        spec.run_id = "other"  # type: ignore[misc]


# ── 7. iteration_reason 默认值 = checkpoint_resume ───────────────


def test_resume_spec_default_iteration_reason() -> None:
    spec = ResumeSpec(
        run_id="r",
        plan_ref="p",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
    )
    assert spec.iteration_reason == "checkpoint_resume"
