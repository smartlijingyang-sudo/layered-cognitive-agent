"""Step Emitter 桥接层单测(ADR-0164 草案 Phase 3)。

覆盖:
- 现有 emit 路径仍写 JournalEvent(stream 不破)
- 同时 step_lifecycle.store 收到对应原语(双写不冲突)
- bridge_* 在 step_lifecycle 没绑的情况下不抛
- bridge_llm_completed 折叠 reasoning + decision
- bridge_tool_invoked 折叠 ok / fail / 文件输出
- bridge_perceive_opened → bridge_perceive_closed 形成完整 step
- bridge_step_completed_emitted 关闭当前 step
- 多次 open/close 的边界条件
"""

from __future__ import annotations

import pytest

from lca.contracts.models.observability import (
    JournalMetadata,
    ToolCallRecord,
)
from lca.infrastructure.observability import facade as fd
from lca.infrastructure.observability.facade.facade import (
    _run_context as _run_ctx_var,
)
from lca.runtime import step_emitter, step_lifecycle


@pytest.fixture
def bound_store() -> object:
    """绑 lifecycle store + _run_context(两者都 facade.step_open 要求)。"""
    store = step_lifecycle.StepLifecycleStore()
    store.bind_run(
        run_id="r1",
        trace_id="t1",
        metadata=JournalMetadata(
            agent_role="agt_test",
            strategy_key="solo",
            plan_ref="plan_001",
            objective="test",
        ),
    )
    store_token = step_lifecycle.set_lifecycle_store(store)
    ctx_token = _run_ctx_var.set(fd.RunContext(run_id="r1", trace_id="t1"))
    try:
        yield store
    finally:
        _run_ctx_var.reset(ctx_token)
        step_lifecycle.reset_lifecycle_store(store_token)


# ── 现有 emit 路径仍工作(stream 不破) ──


def test_record_event_does_not_crash_without_lifecycle_store() -> None:
    """没绑 lifecycle store → 调用 bridge_* 不抛, 只是 silently no-op。"""
    # 当前 task 没 lifecycle store
    step_emitter.bridge_llm_completed(model="m", latency_ms=1)
    step_emitter.bridge_tool_started(
        tool_name="t",
        invocation_id="i",
        arguments={},
    )
    step_emitter.bridge_tool_invoked(
        tool_name="t",
        invocation_id="i",
        ok=True,
        latency_ms=1,
    )
    step_emitter.bridge_tool_denied(tool_name="t", reason="perm")
    step_emitter.bridge_perceive_opened(objective="t")
    step_emitter.bridge_perceive_closed(outcome="ok")
    step_emitter.bridge_think_opened(objective="t")
    step_emitter.bridge_think_closed()
    step_emitter.bridge_act_opened(objective="t")
    step_emitter.bridge_act_closed()
    step_emitter.bridge_step_completed_emitted(status="ok")


# ── LLM bridge ──


def test_bridge_llm_completed_writes_thinking(bound_store: object) -> None:
    step_emitter.bridge_think_opened(objective="test")
    step_emitter.bridge_llm_completed(
        model="qwen3.7-plus",
        latency_ms=100,
        reasoning_preview="let me think",
        prompt_tokens=10,
        completion_tokens=20,
        response_preview="ok",
        decision="use_tool",
    )
    step_emitter.bridge_think_closed(outcome="ok", summary="decide done")
    cur_before = bound_store.get_current_step()
    assert cur_before is None  # 已 close
    # 取出 closed step
    closed = bound_store.get_closed_steps()[0]
    assert closed.thinking is not None
    assert closed.thinking.model == "qwen3.7-plus"
    assert closed.thinking.reasoning == "let me think"
    assert closed.thinking.decision == "use_tool"
    assert closed.thinking.prompt_tokens == 10
    assert closed.thinking.completion_tokens == 20
    assert closed.reflect is not None
    assert closed.reflect.summary == "decide done"
    assert closed.outcome == "ok"


def test_bridge_llm_reasoning_delta_writes_span(bound_store: object) -> None:
    step_emitter.bridge_think_opened(objective="test")
    step_emitter.bridge_llm_reasoning_delta(
        text_delta="hello",
        started_at=1.0,
    )
    step_emitter.bridge_llm_reasoning_delta(
        text_delta=" world",
        started_at=1.1,
    )
    step_emitter.bridge_think_closed()
    closed = bound_store.get_closed_steps()[0]
    reasoning_spans = [s for s in closed.spans if s.kind == "reasoning_delta"]
    assert len(reasoning_spans) == 2
    assert reasoning_spans[0].summary["text_delta"] == "hello"
    assert reasoning_spans[1].summary["text_delta"] == " world"


def test_bridge_llm_step_text_delta_writes_span_with_channel(bound_store: object) -> None:
    step_emitter.bridge_think_opened(objective="test")
    step_emitter.bridge_llm_step_text_delta(
        text_delta="hi",
        channel="decision",
        started_at=1.0,
    )
    step_emitter.bridge_llm_step_text_delta(
        text_delta="answer",
        channel="answer",
        started_at=1.5,
    )
    step_emitter.bridge_think_closed()
    closed = bound_store.get_closed_steps()[0]
    decision_spans = [s for s in closed.spans if s.kind == "step_text_delta:decision"]
    answer_spans = [s for s in closed.spans if s.kind == "step_text_delta:answer"]
    assert len(decision_spans) == 1
    assert len(answer_spans) == 1


# ── Tool bridge ──


def test_bridge_tool_started_writes_tool_call(bound_store: object) -> None:
    step_emitter.bridge_act_opened(objective="t", tool_name="executeCode")
    step_emitter.bridge_tool_started(
        tool_name="executeCode",
        invocation_id="t1",
        arguments={"code": "print(1)"},
        arguments_summary="执行 print(1)",
    )
    step_emitter.bridge_tool_invoked(
        tool_name="executeCode",
        invocation_id="t1",
        ok=True,
        latency_ms=50,
        files_created=("/var/out/a.pdf",),
        delta_summary="✅ 写出 1 个文件: a.pdf",
        stdout_head="1",
        stdout_chars_total=1,
    )
    step_emitter.bridge_act_closed(outcome="ok", summary="ok")
    closed = bound_store.get_closed_steps()[0]
    assert closed.tool_call is not None
    assert closed.tool_call.name == "executeCode"
    assert closed.tool_call.invocation_id == "t1"
    assert closed.tool_call.arguments == {"code": "print(1)"}
    assert closed.tool_call.arguments_summary == "执行 print(1)"
    assert closed.tool_result is not None
    assert closed.tool_result.ok is True
    assert closed.tool_result.files_created == ("/var/out/a.pdf",)
    assert closed.tool_result.delta_summary == "✅ 写出 1 个文件: a.pdf"


def test_bridge_tool_invoked_failure(bound_store: object) -> None:
    step_emitter.bridge_act_opened(objective="t")
    step_emitter.bridge_tool_started(
        tool_name="executeCode",
        invocation_id="t1",
        arguments={"code": "1/0"},
    )
    step_emitter.bridge_tool_invoked(
        tool_name="executeCode",
        invocation_id="t1",
        ok=False,
        latency_ms=100,
        error="ZeroDivisionError",
        delta_summary="❌ ZeroDivisionError",
        stderr="Traceback...",
    )
    step_emitter.bridge_act_closed(outcome="fail", error="ZeroDivisionError")
    closed = bound_store.get_closed_steps()[0]
    assert closed.tool_result is not None
    assert closed.tool_result.ok is False
    assert closed.tool_result.error == "ZeroDivisionError"
    assert closed.tool_result.delta_summary == "❌ ZeroDivisionError"
    assert closed.outcome == "fail"
    assert closed.error == "ZeroDivisionError"


def test_bridge_tool_denied_writes_span(bound_store: object) -> None:
    step_emitter.bridge_act_opened(objective="t")
    step_emitter.bridge_tool_denied(tool_name="bash", reason="permission")
    step_emitter.bridge_act_closed(outcome="fail", error="permission denied")
    closed = bound_store.get_closed_steps()[0]
    denied_spans = [s for s in closed.spans if s.kind == "tool_denied"]
    assert len(denied_spans) == 1
    assert denied_spans[0].summary["tool_name"] == "bash"
    assert denied_spans[0].summary["reason"] == "permission"


# ── Perceive / Think / Act step 边界 ──


def test_bridge_perceive_full_cycle(bound_store: object) -> None:
    opened = step_emitter.bridge_perceive_opened(objective="测试")
    assert opened is not None
    cur = bound_store.get_current_step()
    assert cur is not None
    assert cur.phase == "perceive"
    assert cur.context_before is not None
    assert cur.context_before.objective == "测试"
    step_emitter.bridge_perceive_closed(outcome="ok", summary="感知 3 项")
    assert bound_store.get_current_step() is None
    closed = bound_store.get_closed_steps()[0]
    assert closed.phase == "perceive"
    assert closed.outcome == "ok"
    assert closed.reflect is not None
    assert closed.reflect.summary == "感知 3 项"


def test_bridge_think_full_cycle(bound_store: object) -> None:
    opened = step_emitter.bridge_think_opened(objective="决策")
    assert opened is not None
    cur = bound_store.get_current_step()
    assert cur is not None
    assert cur.phase == "think"
    step_emitter.bridge_think_closed(outcome="ok", summary="ok")
    closed = bound_store.get_closed_steps()[0]
    assert closed.phase == "think"


def test_bridge_act_full_cycle(bound_store: object) -> None:
    opened = step_emitter.bridge_act_opened(objective="执行", tool_name="executeCode")
    assert opened is not None
    cur = bound_store.get_current_step()
    assert cur is not None
    assert cur.phase == "act"
    assert cur.context_before is not None
    assert cur.context_before.extra["initiated_tool"] == "executeCode"
    step_emitter.bridge_act_closed(outcome="ok", summary="done")
    closed = bound_store.get_closed_steps()[0]
    assert closed.phase == "act"


# ── StepCompleted 兼容桥 ──


def test_bridge_step_completed_emitted_closes_current_step(bound_store: object) -> None:
    step_emitter.bridge_think_opened(objective="t")
    step_emitter.bridge_step_completed_emitted(status="working")
    assert bound_store.get_current_step() is None
    closed = bound_store.get_closed_steps()[0]
    assert closed.outcome == "ok"


def test_bridge_step_completed_emitted_failure(bound_store: object) -> None:
    step_emitter.bridge_act_opened(objective="t")
    step_emitter.bridge_step_completed_emitted(status="failed")
    closed = bound_store.get_closed_steps()[0]
    assert closed.outcome == "fail"


def test_bridge_step_completed_without_open_is_silent(bound_store: object) -> None:
    """没 open step 直接 close → silent(不应抛)。"""
    step_emitter.bridge_step_completed_emitted(status="ok")
    # 没有 closed step
    assert bound_store.get_closed_steps() == ()


# ── 多次 open/close 序列 ──


def test_full_3_step_cycle(bound_store: object) -> None:
    """perceive → think → act 三步完整序列。"""
    # step 1: perceive
    step_emitter.bridge_perceive_opened(objective="t")
    step_emitter.bridge_perceive_closed(outcome="ok", summary="感知")

    # step 2: think
    step_emitter.bridge_think_opened(objective="t")
    step_emitter.bridge_llm_completed(
        model="m",
        latency_ms=10,
        decision="use_tool",
        tool_call=ToolCallRecord(
            invocation_id="t1",
            name="executeCode",
            arguments={"code": "print(1)"},
        ),
    )
    step_emitter.bridge_think_closed(outcome="ok", summary="decide")

    # step 3: act
    step_emitter.bridge_act_opened(objective="t")
    step_emitter.bridge_tool_started(
        tool_name="executeCode",
        invocation_id="t1",
        arguments={"code": "print(1)"},
    )
    step_emitter.bridge_tool_invoked(
        tool_name="executeCode",
        invocation_id="t1",
        ok=True,
        latency_ms=50,
        delta_summary="ok",
    )
    step_emitter.bridge_act_closed(outcome="ok", summary="done")

    closed = bound_store.get_closed_steps()
    assert len(closed) == 3
    assert [s.phase for s in closed] == ["perceive", "think", "act"]
    assert [s.outcome for s in closed] == ["ok", "ok", "ok"]
    # step 2 (think) 有 thinking + tool_call
    assert closed[1].thinking is not None
    assert closed[1].thinking.tool_call is not None
    assert closed[1].thinking.tool_call.name == "executeCode"
    # step 3 (act) 有 tool_call + tool_result
    assert closed[2].tool_call is not None
    assert closed[2].tool_result is not None


# ── _summarize_args 测试 —— 通过 tool_journal_emit 触发 ──


def test_summarize_args_truncates_long_values() -> None:
    from lca.cognition.body.tool_journal_emit import _summarize_args

    summary = _summarize_args({"code": "x" * 100, "language": "python"})
    # repr 限 32 字符 + 截断
    assert len(summary) <= 200
    assert "python" in summary


def test_summarize_args_empty() -> None:
    from lca.cognition.body.tool_journal_emit import _summarize_args

    assert _summarize_args({}) == ""


# ── step_emitter 是 silent no-op 测试 ──


def test_step_emitter_does_not_raise_runtime_error_without_store() -> None:
    """run_scope 没绑时, bridge_* 全部 silent。"""
    # 没绑 store
    step_emitter.bridge_llm_completed(model="m", latency_ms=1)
    step_emitter.bridge_tool_started(tool_name="t", invocation_id="i", arguments={})
    step_emitter.bridge_tool_invoked(tool_name="t", invocation_id="i", ok=True, latency_ms=1)
    # 没抛 → pass
    assert True


# ── _try_get_current_step ──


def test_try_get_current_step_returns_none_without_store() -> None:
    assert step_emitter._try_get_current_step() is None


def test_try_get_current_step_returns_draft_when_open() -> None:
    """每个 test 自己初始化 + 清理(避免 fixture 状态泄漏)。"""
    store = step_lifecycle.StepLifecycleStore()
    store.bind_run(
        run_id="r1",
        trace_id="t1",
        metadata=JournalMetadata(
            agent_role="x",
            strategy_key="solo",
            plan_ref="",
            objective="t",
        ),
    )
    store_token = step_lifecycle.set_lifecycle_store(store)
    ctx_token = _run_ctx_var.set(fd.RunContext(run_id="r1", trace_id="t1"))
    try:
        step_emitter.bridge_think_opened(objective="t")
        cur = step_emitter._try_get_current_step()
        assert cur is not None
        assert cur.phase == "think"
    finally:
        _run_ctx_var.reset(ctx_token)
        step_lifecycle.reset_lifecycle_store(store_token)
