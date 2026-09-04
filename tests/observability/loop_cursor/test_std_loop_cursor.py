"""ADR-0169 PR-1:StdLoopCursor 默认实现测试。

使用 stub spine 验证:
- advance 自动派生 phase.<name>.fold EP
- record_* 在正确 phase window 内追加 EP
- step_index / incarnation / seq 计数正确
- close 之后抛 CursorError
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import CursorError
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor import StdLoopCursor


@dataclass
class _StubSpine:
    """捕获 append 调用,返回分配的 seq。"""

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


def _make_cursor() -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=2),
    )
    return cursor, spine


def _req_header(step_id: str = "step-001") -> RequestHeader:
    return RequestHeader(
        step_id=step_id,
        incarnation=2,
        reason="initial",
        model="m",
        tools_digest="td",
        tools_path="tp",
        messages_digest="md",
        messages_path="mp",
        manifest_digest="mf",
        manifest_path="mfp",
    )


def test_advance_emits_phase_fold_ep() -> None:
    c, spine = _make_cursor()
    c.advance("perceive")
    assert len(spine.records) == 1
    assert spine.records[0]["execution_point"] == "phase.perceive.fold"
    assert spine.records[0]["incarnation"] == 2


def test_full_phase_chain_emits_phase_folds() -> None:
    c, spine = _make_cursor()
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    eps = [r["execution_point"] for r in spine.records]
    assert eps == [
        "phase.perceive.fold",
        "phase.think.fold",
        "phase.gate.fold",
        "phase.act.fold",
        "phase.reflect.fold",
        "phase.stop.fold",
    ]


def test_record_thinking_in_think_window_emits_ep() -> None:
    c, spine = _make_cursor()
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="abc",
            content_path=None,
            token_count=100,
            thinking_kind="reasoning",
        )
    )
    assert spine.records[-1]["execution_point"] == "step.thinking.record"
    assert spine.records[-1]["payload"]["incarnation"] == 2
    # 缺省无 text_preview ⇒ payload 不携带该键
    assert "text_preview" not in spine.records[-1]["payload"]


def test_record_thinking_text_preview_forwarded_into_payload() -> None:
    """text_preview 非空时原样进 EP payload;为空时省略(与 record_tool_call arguments 同模式)。"""
    c, spine = _make_cursor()
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="abc",
            content_path="model_visible/step-001/thinking.json",
            token_count=100,
            thinking_kind="final_response",
        ),
        text_preview="the model said this",
    )
    payload = spine.records[-1]["payload"]
    assert spine.records[-1]["execution_point"] == "step.thinking.record"
    assert payload["text_preview"] == "the model said this"
    assert payload["thinking_kind"] == "final_response"
    assert payload["content_path"] == "model_visible/step-001/thinking.json"


def test_record_tool_call_in_act_window() -> None:
    c, spine = _make_cursor()
    c.advance("act")
    c.record_tool_call(
        ToolCallRecord(
            tool_name="t",
            args_digest="x",
            args_payload_path=None,
            call_seq=1,
        )
    )
    assert spine.records[-1]["execution_point"] == "step.tool_call.record"


def test_record_tool_result_in_act_window() -> None:
    c, spine = _make_cursor()
    c.advance("act")
    c.record_tool_result(
        ToolResultRecord(
            tool_name="t",
            result_digest="x",
            result_path=None,
            outcome="ok",
        )
    )
    assert spine.records[-1]["execution_point"] == "step.tool_result.record"


def test_record_request_header_increments_step_index() -> None:
    c, _spine = _make_cursor()
    c.advance("think")
    c.record_request_header(
        RequestHeader(
            step_id="step-001",
            incarnation=2,
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
    assert c.snapshot.step_index == 1
    assert c.snapshot.step_id == "step-001"


def test_record_request_header_emits_step_start_before_header() -> None:
    """ADR-0184 D6:record_request_header 同源同步发射显式边界。

    顺序钉死:``writable.step.start``(边界)先于 ``llm.request.header``
    (边界内的首个事实),与 fold 的边界开窗语法一致。
    """
    c, spine = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    eps = [r["execution_point"] for r in spine.records]
    assert eps[-2:] == ["writable.step.start", "llm.request.header"]
    start = spine.records[-2]
    assert start["payload"] == {
        "step": 1,
        "run_id": "r1",
        "step_id": "step-001",
        "phase": "think",
    }


def test_advance_stop_emits_step_end_when_step_open() -> None:
    """ADR-0184 D6:advance("stop") 收口开窗中的 step。"""
    c, spine = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    c.advance("stop")
    rec = spine.records[-1]
    assert rec["execution_point"] == "writable.step.end"
    assert rec["payload"] == {
        "step": 1,
        "run_id": "r1",
        "step_id": "step-001",
        "outcome": "success",
    }


def test_advance_stop_without_open_step_emits_no_step_end() -> None:
    """无 LLM 边界的 iteration 走到 stop 不补发 writable.step.end。"""
    c, spine = _make_cursor()
    c.advance("perceive")
    c.advance("think")
    c.advance("stop")
    eps = [r["execution_point"] for r in spine.records]
    assert "writable.step.end" not in eps
    assert eps == ["phase.perceive.fold", "phase.think.fold", "phase.stop.fold"]


def test_close_emits_step_end_for_open_step() -> None:
    """ADR-0184 D6:close 是未及 advance("stop") 的 step 的兜底收口。"""
    c, spine = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    c.close("error")
    eps = [r["execution_point"] for r in spine.records]
    # step.end 先于 writable.iteration.closing
    assert eps[-2:] == ["writable.step.end", "writable.iteration.closing"]
    assert spine.records[-2]["payload"]["outcome"] == "cancelled"


def test_close_completed_step_end_outcome_success() -> None:
    c, spine = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    c.close("completed")
    assert spine.records[-2]["payload"]["outcome"] == "success"


def test_close_after_advance_stop_does_not_double_step_end() -> None:
    """advance("stop") 已收口 → close 不重复发 writable.step.end。"""
    c, spine = _make_cursor()
    c.advance("think")
    c.record_request_header(_req_header("step-001"))
    c.advance("stop")
    c.close("completed")
    ends = [r for r in spine.records if r["execution_point"] == "writable.step.end"]
    assert len(ends) == 1


def test_record_thinking_outside_think_raises() -> None:
    c, _ = _make_cursor()
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_thinking(
            ThinkingRecord(
                content_digest="x",
                content_path=None,
                token_count=1,
                thinking_kind="reasoning",
            )
        )


def test_close_emits_closing_ep() -> None:
    c, spine = _make_cursor()
    c.close("completed")
    assert spine.records[-1]["execution_point"] == "writable.iteration.closing"


def test_close_after_close_raises() -> None:
    c, _ = _make_cursor()
    c.close("completed")
    with pytest.raises(CursorError):
        c.close("error")


def test_seq_monotonically_increases() -> None:
    c, spine = _make_cursor()
    c.advance("perceive")
    c.advance("think")
    c.record_thinking(
        ThinkingRecord(
            content_digest="x",
            content_path=None,
            token_count=1,
            thinking_kind="reasoning",
        )
    )
    seqs = [r["seq"] for r in spine.records]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3


def test_fork_produces_independent_child() -> None:
    c, _ = _make_cursor()
    child = c.fork("child_agent")
    assert isinstance(child, StdLoopCursor)
    assert child.snapshot.run_id == "r1"
    assert child.snapshot.phase is None


# ── open_step(LLM 边界 step 推进,hook 路径)─────────────────────


def test_open_step_emits_writable_step_start() -> None:
    """open_step 做 L6 自增 + 落显式 ``writable.step.start`` 边界(ADR-0184 D6)。

    hook 路径自行经 Session 发 ``spine.llm.request.header`` payload;
    cursor 不派生 ``llm.request.header`` EP(双重 step 边),但显式
    step 边界由 cursor 唯一发射。
    """
    c, spine = _make_cursor()
    c.advance("think")
    assert len(spine.records) == 1
    c.open_step("step-001")
    snap = c.snapshot
    assert snap.step_index == 1
    assert snap.step_id == "step-001"
    assert snap.attempt_in_step == 0
    assert len(spine.records) == 2
    rec = spine.records[-1]
    assert rec["execution_point"] == "writable.step.start"
    assert rec["payload"]["step"] == 1
    assert rec["payload"]["step_id"] == "step-001"
    assert rec["payload"]["run_id"] == "r1"
    assert rec["payload"]["phase"] == "think"


def test_open_step_monotonic_across_llm_requests() -> None:
    """连续 LLM 请求逐个 open_step,step_index 单调、step_id 跟随。"""
    c, spine = _make_cursor()
    c.advance("think")
    c.open_step("step-001")
    c.open_step("step-002")
    c.open_step("step-003")
    snap = c.snapshot
    assert snap.step_index == 3
    assert snap.step_id == "step-003"
    # phase.think.fold + 3 条 writable.step.start(每次 LLM 边界一条)
    assert len(spine.records) == 4


def test_open_step_not_bound_to_think_window() -> None:
    """team 委派时子 Agent LLM 边界可能在共享 cursor 的非 think 相位。"""
    c, _ = _make_cursor()
    c.advance("act")
    c.open_step("step-001")
    assert c.snapshot.step_index == 1


def test_open_step_after_close_raises() -> None:
    c, _ = _make_cursor()
    c.close("completed")
    with pytest.raises(CursorError):
        c.open_step("step-001")


def test_open_step_while_halted_raises() -> None:
    c, _ = _make_cursor()
    c.advance("think")
    c.halt("approval_pending")
    with pytest.raises(CursorError):
        c.open_step("step-001")
