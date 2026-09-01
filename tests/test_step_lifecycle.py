"""Step Lifecycle 单测(ADR-0164 草案 Phase 1)。

覆盖:
- bind_run 后才能 open_step
- open_step 拒绝对同一 store 在已有 current 时再次 open
- record_* 拒绝在没有 current step 时调用
- close_step 后 current 清空, 下一次 open_step 允许
- record_* 不可变 —— 当前 step 替换, closed steps 不影响
- close_document 拒绝还有 open step
- summarize_step 5 状态正确(未闭合 / fail / ok / tool-only / think-only)
- prior_summary_chain 跨 step 链式正确
- ContextVar bind: 显式 set_lifecycle_store 后顶层 facade 工作
- 线程安全: 多线程并发 record_span 全部保留
- sub-agent 嵌套: subagent_role 透传, step_id 区分
"""

from __future__ import annotations

import threading

import pytest

from lca.contracts.models.observability import (
    AttachmentRef,
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    SpanRecord,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    append_step,
    compute_duration_ms,
    empty_document,
    make_step_id,
    summarize_step,
)
from lca.runtime.step_lifecycle import (
    StepLifecycleStore,
    close_step,
    get_current_step,
    open_step,
    record_reflect,
    record_thinking,
    reset_lifecycle_store,
    set_lifecycle_store,
)


def _meta() -> JournalMetadata:
    return JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_test_001",
        objective="test objective",
    )


def _attachment() -> AttachmentRef:
    return AttachmentRef(
        attachment_id="att_001",
        name="test.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=1024,
    )


def _context() -> StepContext:
    return StepContext(
        objective="test objective",
        attachments=(_attachment(),),
        prior_summary_chain=(),
    )


# ── bind_run 守卫 ──


def test_open_step_before_bind_run_raises() -> None:
    store = StepLifecycleStore()
    with pytest.raises(RuntimeError, match="bind_run"):
        store.open_step("perceive")


def test_record_before_open_step_raises() -> None:
    store = StepLifecycleStore()
    store.bind_run(
        run_id="r1",
        trace_id="t1",
        metadata=_meta(),
    )
    with pytest.raises(RuntimeError, match="no open step"):
        store.record_thinking(
            ThinkingTrace(model="x", latency_ms=1, decision="respond"),
        )


def test_close_step_without_open_raises() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    with pytest.raises(RuntimeError, match="no open step"):
        store.close_step("ok")


def test_close_document_with_open_step_raises() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    with pytest.raises(RuntimeError, match="still open"):
        store.close_document(outcome="completed")


# ── 5 原语 happy path ──


def test_full_step_lifecycle_records_all_primitives() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    ctx = _context()
    draft = store.open_step("think", context=ctx)
    assert draft.step_id == "step_1"
    assert draft.step_index == 1
    assert draft.phase == "think"
    assert draft.context_before is ctx

    store.record_thinking(
        ThinkingTrace(
            model="qwen3.7-plus",
            latency_ms=1234,
            reasoning="let me decide",
            decision="use_tool",
        ),
    )
    store.record_tool_call(
        ToolCallRecord(
            invocation_id="toolu_001",
            name="executeCode",
            arguments={"code": "print(1)"},
            arguments_summary="执行 Python print(1)",
        ),
    )
    store.record_tool_result(
        ToolResult(
            ok=True,
            latency_ms=500,
            stdout_head="1",
            stdout_chars_total=1,
            delta_summary="成功: 输出 1",
            files_created=("/var/out/out.txt",),
        ),
    )
    store.record_reflect(ReflectTrace(summary="执行成功, 准备下一步", verdict="ok"))

    finalized = store.close_step("ok")
    assert finalized.outcome == "ok"
    assert finalized.thinking is not None
    assert finalized.tool_call is not None
    assert finalized.tool_result is not None
    assert finalized.reflect is not None
    assert finalized.duration_ms is not None
    assert finalized.duration_ms >= 0
    assert finalized.exited_at is not None

    # document 已 append
    assert len(store.document.steps) == 1
    assert store.document.steps[0].step_id == "step_1"
    assert store.get_current_step() is None


def test_partial_step_think_only_no_tool() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("reflect", context=_context())
    store.record_thinking(
        ThinkingTrace(model="x", latency_ms=1, decision="respond"),
    )
    store.record_reflect(ReflectTrace(summary="done thinking"))
    finalized = store.close_step("ok")
    assert finalized.tool_call is None
    assert finalized.tool_result is None


def test_partial_step_perceive_no_thinking() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    finalized = store.close_step("skip")
    assert finalized.thinking is None
    assert finalized.tool_call is None
    assert finalized.reflect is None
    assert finalized.outcome == "skip"


def test_fail_step_records_error() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("act", context=_context())
    store.record_tool_call(
        ToolCallRecord(invocation_id="t1", name="executeCode", arguments={}),
    )
    store.record_tool_result(
        ToolResult(
            ok=False,
            latency_ms=100,
            stderr="LayoutError: too large",
            error="LayoutError: too large",
            delta_summary="❌ 布局溢出",
        ),
    )
    finalized = store.close_step("fail", error="LayoutError")
    assert finalized.outcome == "fail"
    assert finalized.error == "LayoutError"
    assert finalized.tool_result is not None
    assert finalized.tool_result.ok is False


# ── 多 step 序列 / prior_summary_chain ──


def test_multiple_steps_append_to_document() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())

    # step 1
    store.open_step("perceive", context=_context())
    store.close_step("ok")
    # step 2
    store.open_step("think", context=_context())
    store.close_step("ok")
    # step 3
    store.open_step("act", context=_context())
    store.close_step("ok")

    assert len(store.document.steps) == 3
    assert [s.step_index for s in store.document.steps] == [1, 2, 3]
    assert [s.phase for s in store.document.steps] == ["perceive", "think", "act"]

    chain = store.document.prior_summary_chain()
    assert len(chain) == 3


def test_open_step_blocked_when_previous_open() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    with pytest.raises(RuntimeError, match="still open"):
        store.open_step("think")


def test_open_step_resumes_after_close() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    store.close_step("ok")
    # 第二次 ok
    store.open_step("think", context=_context())
    store.close_step("ok")
    assert len(store.document.steps) == 2


# ── spans ──


def test_record_span_appends_in_order() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("act", context=_context())
    for i in range(5):
        store.record_span(
            SpanRecord(
                kind="tool_retry_progress",
                started_at=1000.0 + i,
                summary={"attempt": i},
            ),
        )
    finalized = store.close_step("ok")
    assert len(finalized.spans) == 5
    assert [s.summary["attempt"] for s in finalized.spans] == [0, 1, 2, 3, 4]


# ── 不可变 ──


def test_record_does_not_mutate_closed_step() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("act", context=_context())
    store.record_tool_call(
        ToolCallRecord(invocation_id="t1", name="executeCode", arguments={}),
    )
    finalized = store.close_step("ok")
    closed_id = id(finalized)

    # 第二次 open + record
    store.open_step("act", context=_context())
    store.record_tool_call(
        ToolCallRecord(invocation_id="t2", name="exportFile", arguments={}),
    )
    store.close_step("ok")

    # finalized 不变
    assert id(store.document.steps[0]) == closed_id
    assert store.document.steps[0].tool_call.invocation_id == "t1"
    assert store.document.steps[1].tool_call.invocation_id == "t2"


# ── reset_run ──


def test_reset_run_clears_state() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    store.close_step("ok")
    assert len(store.document.steps) == 1
    store.reset_run()
    assert store.document is None
    assert store.run_id == ""
    assert store.get_current_step() is None


# ── ContextVar / 顶层函数 ──


def test_module_level_facade_requires_bound_store() -> None:
    # 不重置可能残留(测试之间)
    reset_lifecycle_store(set_lifecycle_store(StepLifecycleStore()))
    # 此时 store 已 bind_run 是空状态
    with pytest.raises(RuntimeError, match="lifecycle store"):
        open_step("perceive")


def test_module_level_facade_uses_bound_store() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    token = set_lifecycle_store(store)
    try:
        open_step("perceive", context=_context())
        record_thinking(ThinkingTrace(model="x", latency_ms=1, decision="respond"))
        record_reflect(ReflectTrace(summary="done"))
        close_step("ok")
        # get_current_step 必须 None(已 close)
        assert get_current_step() is None
        assert len(store.document.steps) == 1
        assert store.document.steps[0].phase == "perceive"
    finally:
        reset_lifecycle_store(token)


# ── 线程安全 ──


def test_concurrent_record_span_preserves_all() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("act", context=_context())

    n_threads = 8
    per_thread = 25

    def worker(thread_id: int) -> None:
        for i in range(per_thread):
            store.record_span(
                SpanRecord(
                    kind="hook_triggered",
                    started_at=thread_id * 1000 + i,
                    summary={"thread": thread_id, "i": i},
                ),
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    finalized = store.close_step("ok")
    assert len(finalized.spans) == n_threads * per_thread


# ── sub-agent 嵌套 ──


def test_subagent_step_id_includes_role() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    # 主 step
    store.open_step("think", context=_context())
    store.close_step("ok")
    # 子 step
    draft = store.open_step("act", context=_context(), subagent_role="agt_sub")
    assert draft.step_id == "agt_sub:step_2"
    assert draft.subagent_role == "agt_sub"
    assert draft.parent_step_id == "step_1"  # 主 step 的 id
    store.close_step("ok")


# ── helpers ──


def test_make_step_id_with_and_without_role() -> None:
    assert make_step_id(1) == "step_1"
    assert make_step_id(2, "sub") == "sub:step_2"


def test_compute_duration_ms() -> None:
    assert compute_duration_ms(1000.0, 1001.5) == 1500
    assert compute_duration_ms(1000.0, 999.0) == 0  # 防负
    assert compute_duration_ms(1000.0, None) is None


def test_summarize_step_in_progress() -> None:
    from lca.contracts.models.observability import JournalStep

    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="think",
        entered_at=0.0,
        outcome=None,
    )
    assert "in progress" in summarize_step(step)


def test_summarize_step_fail_with_error() -> None:
    from lca.contracts.models.observability import JournalStep

    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="act",
        entered_at=0.0,
        exited_at=1.0,
        outcome="fail",
        error="LayoutError",
    )
    assert "fail" in summarize_step(step)
    assert "LayoutError" in summarize_step(step)


def test_summarize_step_fail_from_tool_result() -> None:
    """tool_result.error 也要被 capture 进 fail summary。"""
    from lca.contracts.models.observability import JournalStep

    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="act",
        entered_at=0.0,
        exited_at=1.0,
        outcome="fail",
        tool_result=ToolResult(
            ok=False,
            latency_ms=100,
            error="timeout",
        ),
    )
    summary = summarize_step(step)
    assert "timeout" in summary


def test_summarize_step_ok_with_reflect() -> None:
    from lca.contracts.models.observability import JournalStep

    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="act",
        entered_at=0.0,
        exited_at=1.0,
        outcome="ok",
        reflect=ReflectTrace(summary="done"),
    )
    assert "done" in summarize_step(step)


def test_summarize_step_ok_with_tool_only() -> None:
    from lca.contracts.models.observability import JournalStep

    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="act",
        entered_at=0.0,
        exited_at=1.0,
        outcome="ok",
        tool_call=ToolCallRecord(invocation_id="t", name="executeCode", arguments={}),
    )
    assert "executeCode" in summarize_step(step)


# ── document 不可变 append ──


def test_append_step_is_immutable() -> None:

    doc = empty_document(
        run_id="r1",
        trace_id="t1",
        metadata=_meta(),
        started_at=0.0,
    )
    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="perceive",
        entered_at=0.0,
        outcome="ok",
    )
    new_doc = append_step(doc, step)
    assert len(doc.steps) == 0
    assert len(new_doc.steps) == 1


def test_close_document_records_outcome() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())
    store.open_step("perceive", context=_context())
    store.close_step("ok")
    closed = store.close_document(outcome="completed", closed_at=2000.0)
    assert closed.metadata.outcome == "completed"
    assert closed.closed_at == 2000.0
    assert closed.metadata.total_steps == 1


def test_cumulative_files_dedup() -> None:
    store = StepLifecycleStore()
    store.bind_run(run_id="r1", trace_id="t1", metadata=_meta())

    store.open_step("act", context=_context())
    store.record_tool_call(
        ToolCallRecord(invocation_id="t1", name="executeCode", arguments={}),
    )
    store.record_tool_result(
        ToolResult(ok=True, latency_ms=1, files_created=("/var/out/a.pdf",)),
    )
    store.close_step("ok")

    store.open_step("act", context=_context())
    store.record_tool_call(
        ToolCallRecord(invocation_id="t2", name="exportFile", arguments={}),
    )
    store.record_tool_result(
        ToolResult(
            ok=True,
            latency_ms=1,
            files_created=("/var/out/a.pdf", "/var/out/b.txt"),
        ),
    )
    store.close_step("ok")

    files = store.document.cumulative_files()
    assert files == ("/var/out/a.pdf", "/var/out/b.txt")  # 去重 + 保序
