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
            system_digest="d1",
            system_path="p1",
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
