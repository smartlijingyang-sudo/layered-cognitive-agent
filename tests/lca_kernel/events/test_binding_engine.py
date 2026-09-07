"""JournalBindingEngine tests (ADR-0198 P1)."""

from __future__ import annotations

from lca.contracts.models.observability.journal.step import ToolCallRecord, ToolResult
from lca.plugins.session.derivers.step_tree.journal_fold import (
    fold_step_tree,
    reset_journal_binding_engine,
)
from lca_kernel.events.compile.compiler import reset_compiled_plan_cache
from lca_kernel.events.fold.binding_engine import (
    JournalBindingEngine,
    extract_from_payload,
    header_model_from_payload,
)


def setup_function() -> None:
    reset_compiled_plan_cache()
    reset_journal_binding_engine()


def test_extract_alternate_paths() -> None:
    payload = {"tool_name": "grep", "name": "search"}
    assert extract_from_payload(payload, "payload.tool_name|payload.name") == "grep"


def test_header_model_from_config() -> None:
    payload = {"config": {"model": "gpt-test", "provider": "openai"}}
    assert header_model_from_payload(payload) == "gpt-test"


def test_body_tool_execute_does_not_clobber_evidence() -> None:
    engine = JournalBindingEngine()
    rich = ToolCallRecord(
        invocation_id="inv-1",
        name="grep",
        arguments={"pattern": "foo"},
        arguments_summary='{"pattern":"foo"}',
    )
    span_payload = {"tool_name": "grep", "invocation_id": "inv-1", "arguments": {}}
    merged = engine.apply_tool_call(rich, span_payload, "body.tool.execute.start")
    assert merged.arguments == {"pattern": "foo"}
    assert merged.arguments_summary == '{"pattern":"foo"}'


def test_tool_result_fill_empty_only() -> None:
    engine = JournalBindingEngine()
    rich = ToolResult(
        ok=True,
        latency_ms=12,
        stdout_head="hello",
        stdout_chars_total=5,
        stdout_truncated=False,
        stderr="",
        files_created=(),
        error=None,
        delta_summary="done",
    )
    span_payload = {"ok": False, "stdout_head": "", "latency_ms": 0}
    merged = engine.apply_tool_result(rich, span_payload, "body.tool.execute.end")
    assert merged.ok is True
    assert merged.stdout_head == "hello"


def test_phase_think_fold_model_name() -> None:
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {
            "execution_point": "phase.think.fold",
            "payload": {"objective_kind": "model_name", "objective": "claude-test"},
            "when": 1.1,
        },
        {"execution_point": "brain.think.end", "payload": {}, "when": 2.0},
    ]
    doc = fold_step_tree(events, run_id="r_model", outcome="completed")
    assert doc.steps[0].thinking is not None
    assert doc.steps[0].thinking.model == "claude-test"


def test_header_model_from_config_payload() -> None:
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {
                "step_id": "step-001",
                "config": {"model": "gpt-config"},
            },
            "when": 1.0,
        },
        {"execution_point": "writable.step.end", "payload": {"outcome": "success"}, "when": 2.0},
    ]
    doc = fold_step_tree(events, run_id="r_header", outcome="completed")
    assert doc.steps[0].thinking is not None
    assert doc.steps[0].thinking.model == "gpt-config"


# ── 回归锁 run_1f5360d2fa47:fold invariant 检测 ok=True+error 矛盾 ──────────


def test_apply_tool_result_raises_on_ok_true_with_nonempty_error() -> None:
    """ok=True 与 error 非空矛盾 → FoldConsistencyError,阻断失真事实落地。

    回归锁 run_1f5360d2fa47:journal 中 ``tool_result.ok=True`` 配
    ``error="exit_code=127"`` 即属此类矛盾样本。
    """
    import pytest

    from lca_kernel.events.fold.binding_engine import FoldConsistencyError

    engine = JournalBindingEngine()
    with pytest.raises(FoldConsistencyError, match="tool_result contradiction"):
        engine.apply_tool_result(
            existing=None,
            payload={
                "tool_name": "runCommand",
                "ok": True,
                "error": "exit_code=127",
            },
            execution_point="step.tool_result.record",
        )


def test_apply_tool_result_accepts_ok_false_with_error() -> None:
    """ok=False + error 非空 → 正常落地,ToolResult.ok=False,error 保留。"""
    engine = JournalBindingEngine()
    result = engine.apply_tool_result(
        existing=None,
        payload={
            "tool_name": "runCommand",
            "ok": False,
            "error": "sh: 1: pdftotext: not found",
        },
        execution_point="step.tool_result.record",
    )
    assert result.ok is False
    assert "pdftotext" in (result.error or "")


def test_apply_tool_result_accepts_ok_true_without_error() -> None:
    """ok=True + error 为 None/空 → 正常落地。"""
    engine = JournalBindingEngine()
    result = engine.apply_tool_result(
        existing=None,
        payload={
            "tool_name": "runCommand",
            "ok": True,
            "error": None,
        },
        execution_point="step.tool_result.record",
    )
    assert result.ok is True
    assert not result.error


def test_apply_tool_result_default_ok_is_false_when_missing() -> None:
    """第一性原则:fold 默认 ok=False(缺 ok 视为失败,防御默认)。"""
    engine = JournalBindingEngine()
    result = engine.apply_tool_result(
        existing=None,
        payload={"tool_name": "runCommand"},
        execution_point="step.tool_result.record",
    )
    assert result.ok is False
