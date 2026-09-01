"""facade step API 单测(ADR-0164 草案 Phase 2)。

覆盖:
- facade.step_open 等 7 个 API 转发到 step_lifecycle
- _require_run_bound 守卫: 没 bind context → RuntimeError
- facade 跟 step_lifecycle 共用 ContextVar store
- facade.step_get_lifecycle_store 给 boot 装配用
- facade.step_close_document 触发 store.close_document
- StepGroupedBackend.write_document 跟 facade 集成
- StepGroupedBackend.write(event) 旧路径发 warning + 返回 None
- StepGroupedBackend.flush 不写未 close 的 document
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from lca.contracts.models.observability import (
    JournalMetadata,
    ReflectTrace,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.infrastructure.observability import facade as fd
from lca.infrastructure.observability.facade.facade import _run_context as _run_ctx_var
from lca.infrastructure.observability.journal.step import (
    StepGroupedBackend,
    read_step_document,
)
from lca.runtime import step_lifecycle


@pytest.fixture
def bound_run_context() -> object:
    """每个 case 都 bind 一个 fresh context + 清 lifecycle store。"""
    _run_ctx_var.set(fd.RunContext(run_id="r1", trace_id="t1"))
    yield
    _run_ctx_var.set(fd.RunContext())


@pytest.fixture
def unbound_run_context() -> object:
    """每个 case 都不 bind context(测 _require_run_bound 守卫)。"""
    _run_ctx_var.set(None)  # type: ignore[arg-type]
    yield
    _run_ctx_var.set(fd.RunContext())


@pytest.fixture
def bound_lifecycle_store() -> object:
    """绑一个 fresh StepLifecycleStore。"""
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
    token = step_lifecycle.set_lifecycle_store(store)
    yield store
    step_lifecycle.reset_lifecycle_store(token)


# ── 守卫 ──


def test_step_open_without_context_raises(unbound_run_context: object) -> None:
    """没 bind _run_context → facade 拒绝。"""
    # 确保 lifecycle store 也没有
    with contextlib.suppress(TypeError, LookupError):
        step_lifecycle.reset_lifecycle_store(step_lifecycle.set_lifecycle_store(None))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="bound run context"):
        fd.step_open("think")


def test_step_record_thinking_without_context_raises(unbound_run_context: object) -> None:
    with pytest.raises(RuntimeError, match="bound run context"):
        fd.step_record_thinking(ThinkingTrace(model="x", latency_ms=1, decision="respond"))


def test_step_close_without_context_raises(unbound_run_context: object) -> None:
    with pytest.raises(RuntimeError, match="bound run context"):
        fd.step_close("ok")


# ── 正常路径 ──


def test_step_open_via_facade_creates_step(
    bound_run_context: object, bound_lifecycle_store: object
) -> None:
    fd.step_open("perceive", context=StepContext(objective="test"))
    cur = fd.step_get_lifecycle_store().get_current_step()
    assert cur is not None
    assert cur.phase == "perceive"


def test_full_step_lifecycle_via_facade(
    bound_run_context: object, bound_lifecycle_store: object
) -> None:
    fd.step_open("think", context=StepContext(objective="test"))
    fd.step_record_thinking(
        ThinkingTrace(model="qwen3.7-plus", latency_ms=100, decision="use_tool"),
    )
    fd.step_record_tool_call(
        ToolCallRecord(invocation_id="t1", name="executeCode", arguments={}),
    )
    fd.step_record_tool_result(
        ToolResult(ok=True, latency_ms=50, delta_summary="ok"),
    )
    fd.step_record_reflect(ReflectTrace(summary="done"))
    fd.step_close("ok")

    store = fd.step_get_lifecycle_store()
    assert store.get_current_step() is None
    assert len(store.get_closed_steps()) == 1


def test_step_record_span_without_open_raises(
    bound_run_context: object, bound_lifecycle_store: object
) -> None:
    """没 open step 直接 record_span → 抛(由 step_lifecycle 守卫)。"""
    from lca.contracts.models.observability import SpanRecord

    with pytest.raises(RuntimeError, match="no open step"):
        fd.step_record_span(SpanRecord(kind="x", started_at=0.0))


# ── facade 与 backend 集成 ──


def test_step_close_document_returns_document(
    bound_run_context: object, bound_lifecycle_store: object
) -> None:
    fd.step_open("perceive", context=StepContext(objective="t"))
    fd.step_close("ok")
    doc = fd.step_close_document(outcome="completed")
    assert doc is not None
    assert doc.metadata.outcome == "completed"


def test_step_grouped_backend_writes_via_facade(
    tmp_path: Path, bound_run_context: object, bound_lifecycle_store: object
) -> None:
    """facade → step_lifecycle → backend.write_document 完整链路。"""
    output = tmp_path / "journal.json"
    store = fd.step_get_lifecycle_store()
    backend = StepGroupedBackend(output_path=output, lifecycle_store=store)

    fd.step_open("think", context=StepContext(objective="test"))
    fd.step_record_thinking(
        ThinkingTrace(model="m", latency_ms=1, reasoning="r", decision="respond"),
    )
    fd.step_record_reflect(ReflectTrace(summary="完成"))
    fd.step_close("ok")
    doc = fd.step_close_document(outcome="completed")
    assert doc is not None

    # 落盘
    backend.write_document(doc)
    assert output.exists()
    # 读回校验
    restored = read_step_document(output)
    assert restored.metadata.objective == "test"
    assert restored.steps[0].thinking.reasoning == "r"


def test_step_grouped_backend_flush_only_when_closed(
    tmp_path: Path, bound_run_context: object, bound_lifecycle_store: object
) -> None:
    """flush 时若 document.closed_at is None → 不写半截。"""
    output = tmp_path / "journal.json"
    store = fd.step_get_lifecycle_store()
    backend = StepGroupedBackend(output_path=output, lifecycle_store=store)

    fd.step_open("perceive", context=StepContext(objective="t"))
    fd.step_close("ok")
    # 没 close_document → flush 不写
    backend.flush()
    assert not output.exists()

    # close_document 之后 flush 写
    fd.step_close_document(outcome="completed")
    backend.flush()
    assert output.exists()


def test_step_grouped_backend_write_event_is_deprecated(
    tmp_path: Path, bound_run_context: object, bound_lifecycle_store: object
) -> None:
    """旧路径 write(event) → no-op + warning。"""
    from lca.contracts.models.observability.journal import RuntimeObserved

    output = tmp_path / "journal.json"
    store = fd.step_get_lifecycle_store()
    backend = StepGroupedBackend(output_path=output, lifecycle_store=store)

    result = backend.write(
        RuntimeObserved(operation="test.op", source="test"),
    )
    assert result is None
    # 不应有副作用
    assert not output.exists()


def test_step_grouped_backend_close_runs_flush(
    tmp_path: Path, bound_run_context: object, bound_lifecycle_store: object
) -> None:
    """close() 触发 flush, 已 close 的 document 应落盘。"""
    output = tmp_path / "journal.json"
    store = fd.step_get_lifecycle_store()
    backend = StepGroupedBackend(output_path=output, lifecycle_store=store)
    fd.step_open("perceive", context=StepContext(objective="t"))
    fd.step_close("ok")
    fd.step_close_document(outcome="completed")
    backend.close()
    assert output.exists()
