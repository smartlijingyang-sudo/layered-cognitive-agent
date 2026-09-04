"""fold_step_tree cursor 词表语法 + Session 形态词表归一(回归:run_b2c1424d93d4)。

覆盖:
- Session 形态事件(``type`` 为 ``spine.*`` CATEGORY 前缀)经反查表归一后参与 fold
- ``llm.request.header`` step 边界:开 / 关 / step_id 兜底 / model 留帧
- ``step.thinking.record`` ThinkingTrace attach(text_preview 防御读)
- 残留 open step 的终态收口语义
"""

from __future__ import annotations

from lca.contracts.models.observability.journal_step import ThinkingTrace
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree
from lca_kernel.events.session import SessionEvent

# ── Session 形态(spine.* CATEGORY 前缀)归一 ──────────────────────


def test_session_shaped_prefixed_events_fold_step_and_outcome() -> None:
    """spine.cognition.brain.think.* 开/关 think step;publisher completed 定终态。"""
    events = [
        SessionEvent(
            type="spine.cognition.brain.think.start",
            seq=0,
            time=1_788_512_185_993,
            data={"state_id": "trace_x"},
        ),
        SessionEvent(
            type="spine.cognition.brain.think.end",
            seq=1,
            time=1_788_512_188_840,
            data={"state_id": "trace_x", "outcome": "success"},
        ),
        SessionEvent(
            type="spine.runtime.event_publisher.publish",
            seq=2,
            time=1_788_512_188_973,
            data={"event_type": "completed", "outcome": "success"},
        ),
    ]
    doc = fold_step_tree(events, run_id="r_session_shape")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].phase == "think"
    assert doc.steps[0].outcome == "success"
    assert doc.metadata.outcome == "completed"


def test_session_shaped_mapping_prefixed_phase_fold_and_unknown_passthrough() -> None:
    """``type``/``data`` Mapping 同样经反查归一;未登记 type 原样透传被 skip。"""
    events = [
        {"type": "AgentRunStarted", "data": {"run_id": "r_map"}, "time": 1_788_512_185_000},
        {
            "type": "spine.phase.perceive.fold",
            "data": {"summary": ""},
            "time": 1_788_512_185_100,
        },
        {
            "type": "spine.phase.think.fold",
            "data": {"summary": "respond"},
            "time": 1_788_512_186_000,
        },
    ]
    doc = fold_step_tree(events, run_id="r_map_shape")
    assert doc.totals is not None
    assert doc.totals.phases == 2
    assert [p.kind for p in doc.phases] == ["perceive", "think"]
    assert doc.totals.steps == 0


# ── llm.request.header step 边界 ─────────────────────────────────


def test_llm_request_header_opens_step_with_payload_identity() -> None:
    """header 以 payload step_id 开新 step;run completed 时残留 step 收 success。"""
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "qwen3.7-plus", "reason": "initial"},
            "when": 1_788_512_186.015,
        },
    ]
    doc = fold_step_tree(events, run_id="r_header", outcome="completed")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    step = doc.steps[0]
    assert step.step_id == "step-001"
    assert step.phase == "think"
    assert step.outcome == "success"


def test_second_header_closes_first_step() -> None:
    """第二个 header 先以 success 关闭前一步,再开新 step。"""
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "m", "reason": "initial"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-002", "model": "m", "reason": "tool_result"},
            "when": 1_788_512_190.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_two_headers")
    assert doc.totals is not None
    assert doc.totals.steps == 2
    first, second = doc.steps
    assert first.step_id == "step-001"
    assert first.outcome == "success"
    assert first.exited_at is not None
    assert second.step_id == "step-002"
    # 无终态信号 → 残留 step 维持 cancelled
    assert second.outcome == "cancelled"


def test_header_without_step_id_generates_sequential_id() -> None:
    """payload 缺 step_id 时回落生成 step_{seq:03d}。"""
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"model": "m", "reason": "initial"},
            "when": 1_788_512_186.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_header_seq", outcome="completed")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step_001"


def test_header_upgrades_empty_think_frame_in_place() -> None:
    """DSH 切步:brain.think.start 开的空隐式帧被 header 原地升级,一步一次模型请求。"""
    events = [
        {
            "execution_point": "brain.think.start",
            "payload": {"state_id": "s"},
            "when": 1_788_512_185.9,
        },
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "qwen3.7-plus", "reason": "initial"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "brain.think.end",
            "payload": {"state_id": "s", "outcome": "success"},
            "when": 1_788_512_188.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_merge", outcome="completed")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].step_id == "step-001"
    assert doc.steps[0].outcome == "success"


def test_header_after_thinking_opens_new_step() -> None:
    """隐式 think 帧已有 thinking 内容时,后续 header 关旧步开新步(两次模型请求)。"""
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1_788_512_185.0},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "m", "reason": "initial"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "step.thinking.record",
            "payload": {"text_preview": "t", "step_index": 1},
            "when": 1_788_512_187.0,
        },
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-002", "model": "m", "reason": "next_step"},
            "when": 1_788_512_190.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_two_real_steps")
    assert doc.totals is not None
    assert [s.step_id for s in doc.steps] == ["step-001", "step-002"]
    assert doc.steps[0].thinking is not None
    assert doc.steps[0].outcome == "success"
    # 第二步仍开着,无终态信号 → materialize 按 cancelled 收口
    assert doc.steps[1].outcome == "cancelled"


# ── step.thinking.record ─────────────────────────────────────────


def test_step_thinking_record_attaches_thinking_trace_with_text_preview() -> None:
    """ThinkingTrace.model 取自 header 开 step 的帧;text_preview 进 reasoning。"""
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "qwen3.7-plus", "reason": "initial"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "step.thinking.record",
            "payload": {
                "text_preview": "用户问的是一个简单的数学问题。",
                "content_path": "model_visible/step-001/thinking.txt",
                "token_count": 55,
                "step_index": 1,
            },
            "when": 1_788_512_188.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_thinking", outcome="completed")
    assert len(doc.steps) == 1
    assert doc.steps[0].thinking == ThinkingTrace(
        model="qwen3.7-plus",
        latency_ms=0,
        reasoning="用户问的是一个简单的数学问题。",
        raw_response_preview="model_visible/step-001/thinking.txt",
        completion_tokens=55,
    )


def test_step_thinking_record_defensive_without_text_preview() -> None:
    """payload 缺 text_preview(cursor 当前形态)时回落 content_digest,不抛。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "step.thinking.record",
            "payload": {"content_digest": "sha256:abc", "step_index": 1},
            "when": 1_788_512_188.0,
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": 1_788_512_189.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_thinking_defensive")
    thinking = doc.steps[0].thinking
    assert thinking is not None
    assert thinking.reasoning == ""
    assert thinking.raw_response_preview == "sha256:abc"
    assert thinking.completion_tokens is None
    assert thinking.model == ""


# ── 残留 open step 终态语义 ──────────────────────────────────────


def test_residual_open_step_closes_success_on_terminal_completed() -> None:
    """kernel.run.stop success → 残留 open step 以 success 收口。"""
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001"},
            "when": 1_788_512_186.0,
        },
        {
            "execution_point": "kernel.run.stop",
            "payload": {},
            "outcome": "success",
            "when": 1_788_512_190.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_residual_ok")
    assert doc.steps[0].outcome == "success"
    assert doc.metadata.outcome == "completed"
