"""Step Lifecycle — runtime 显式 step 边界管理 (ADR-0164 草案)。

核心不变量:
    - **顶层真相是 step 树**, 不是 seq 流水。 一个 step 闭合后才能开
      下一个; close_step 未调用 → open_step 拒绝(防漂移)。
    - **单写者**: StepLifecycleStore 由 runtime 持有, 通过 ContextVar
      暴露 current step 给 runtime 任意层调用。 ContextVar 是 per-task
      的, 跟 asyncio 协同安全。
    - **不可变 step**: step 在 close 之前是 draft, close 时由 store 写
      入 finalized tuple, 不在原地改。 跨步 prior_summary_chain 是
      不可变 snapshot。

API 形状 (5 原语 + 3 边界):
    open_step(phase) → JournalStep draft
    record_thinking(trace)   → 写入 draft.thinking
    record_tool_call(call)   → 写入 draft.tool_call
    record_tool_result(result) → 写入 draft.tool_result
    record_reflect(trace)   → 写入 draft.reflect
    record_span(span)       → append draft.spans (不可变)
    close_step(outcome, error?) → finalize, append 到 store
    get_current_step() → Optional[JournalStep]
    reset_run(run_id) → 清空 store(测试 / 新 run 起点)

子 agent: subagent_role 透传, 不重置 store。 open_step(parent=...) 会
把当前 draft 的 parent_step_id 设为父 step_id(嵌套), step_id 用
``<role>:step_<index>`` 区分。

不做的事:
    - 不持久化到 journal.json —— 由 projector 收口(Phase 2)。
    - 不做 race condition 处理 —— 假设 runtime 单写者; 真有竞争
      应该用 actor, 不在 step_lifecycle 层处理。
    - 不发事件到 EventBus —— step 是 journal 真值, 不再发 stream。
"""

from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from lca.contracts.models.observability.journal_doc import (
    JournalDocument,
    JournalMetadata,
    append_step,
    close_document,
    empty_document,
)
from lca.contracts.models.observability.journal_step import (
    JournalStep,
    ReflectTrace,
    SpanRecord,
    StepContext,
    StepOutcome,
    StepPhase,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    compute_duration_ms,
    make_step_id,
)

# ── 单写者 store ────────────────────────────────────────


@dataclass
class StepLifecycleStore:
    """线程安全的 step lifecycle store(per-run 单例)。

    runtime 持有, ContextVar 暴露 current step。 多个 run 不能共享同一
    store —— 切换 run 时必须 ``reset_run()``。
    """

    run_id: str = ""
    trace_id: str = ""
    document: JournalDocument | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _current: JournalStep | None = None
    _step_counter: int = 0
    _closed_steps: tuple[JournalStep, ...] = ()

    def bind_run(
        self,
        *,
        run_id: str,
        trace_id: str,
        metadata: JournalMetadata,
        started_at: float | None = None,
    ) -> JournalDocument:
        """绑定新 run。 旧 store 内容清空(防御: 跨 run 复用风险)。"""
        with self._lock:
            self.run_id = run_id
            self.trace_id = trace_id
            self.document = empty_document(
                run_id=run_id,
                trace_id=trace_id,
                metadata=metadata,
                started_at=started_at if started_at is not None else time.time(),
            )
            self._current = None
            self._step_counter = 0
            self._closed_steps = ()
            return self.document

    def open_step(
        self,
        phase: StepPhase,
        *,
        subagent_role: str | None = None,
        context: StepContext | None = None,
        parent_step_id: str | None = None,
    ) -> JournalStep:
        """开 step —— 拒绝在已有 current step 时调用。"""
        with self._lock:
            if self.document is None:
                raise RuntimeError(
                    "open_step called before bind_run; "
                    "call StepLifecycleStore.bind_run(run_id=..., ...) first"
                )
            if self._current is not None:
                raise RuntimeError(
                    f"open_step({phase!r}) called while step "
                    f"{self._current.step_id!r} is still open. "
                    f"Call close_step() on the previous step first."
                )
            self._step_counter += 1
            step_id = make_step_id(self._step_counter, subagent_role)
            draft = JournalStep(
                step_id=step_id,
                step_index=self._step_counter,
                phase=phase,
                entered_at=time.time(),
                parent_step_id=parent_step_id
                if parent_step_id is not None
                else self._last_closed_id(subagent_role=subagent_role),
                subagent_role=subagent_role,
                context_before=context,
            )
            self._current = draft
            return draft

    def _last_closed_id(self, *, subagent_role: str | None) -> str | None:
        """最近闭合的 step_id(用于 parent_step_id)。

        优先匹配同 subagent_role, 找不到 → 取任意最近 step(solo run
        主 step 跟 sub-agent step 的简单链式)。
        """
        for step in reversed(self._closed_steps):
            if step.subagent_role == subagent_role:
                return step.step_id
        if self._closed_steps:
            return self._closed_steps[-1].step_id
        return None

    def _update_current(self, **changes: Any) -> JournalStep:
        """在锁内更新 draft(不可变 replace)。"""
        if self._current is None:
            raise RuntimeError("update_current: no open step")
        new = replace(self._current, **changes)
        self._current = new
        return new

    def record_thinking(self, trace: ThinkingTrace) -> None:
        with self._lock:
            if self._current is None:
                raise RuntimeError("record_thinking: no open step")
            self._update_current(thinking=trace)

    def record_tool_call(self, call: ToolCallRecord) -> None:
        with self._lock:
            if self._current is None:
                raise RuntimeError("record_tool_call: no open step")
            self._update_current(tool_call=call)

    def record_tool_result(self, result: ToolResult) -> None:
        with self._lock:
            if self._current is None:
                raise RuntimeError("record_tool_result: no open step")
            self._update_current(tool_result=result)

    def record_reflect(self, reflect: ReflectTrace) -> None:
        with self._lock:
            if self._current is None:
                raise RuntimeError("record_reflect: no open step")
            self._update_current(reflect=reflect)

    def record_span(self, span: SpanRecord) -> None:
        with self._lock:
            if self._current is None:
                raise RuntimeError("record_span: no open step")
            new_spans = (*self._current.spans, span)
            self._update_current(spans=new_spans)

    def close_step(
        self,
        outcome: StepOutcome,
        *,
        error: str | None = None,
    ) -> JournalStep:
        """闭合当前 step, append 到 closed_steps + document.steps。

        闭合后 current 清空, 允许下一次 open_step。
        """
        with self._lock:
            if self._current is None:
                raise RuntimeError("close_step: no open step")
            now = time.time()
            finalized = replace(
                self._current,
                exited_at=now,
                duration_ms=compute_duration_ms(self._current.entered_at, now),
                outcome=outcome,
                error=error,
            )
            self._closed_steps = (*self._closed_steps, finalized)
            if self.document is None:
                raise RuntimeError("close_step: document not bound")
            self.document = append_step(self.document, finalized)
            self._current = None
            return finalized

    def get_current_step(self) -> JournalStep | None:
        """读取当前 draft step(不开新 step, 给 hook/UI 探针用)。"""
        with self._lock:
            return self._current

    def get_closed_steps(self) -> tuple[JournalStep, ...]:
        with self._lock:
            return self._closed_steps

    def close_document(
        self,
        *,
        outcome: Literal["completed", "failed", "paused", "stopped"],
        closed_at: float | None = None,
    ) -> JournalDocument:
        """闭合 run document。 必须所有 step 都已 close。"""
        with self._lock:
            if self._current is not None:
                raise RuntimeError(f"close_document: step {self._current.step_id!r} still open")
            if self.document is None:
                raise RuntimeError("close_document: document not bound")
            self.document = close_document(
                self.document,
                outcome=outcome,
                closed_at=closed_at if closed_at is not None else time.time(),
            )
            return self.document

    def reset_run(self) -> None:
        """清空 store(测试 / 跨 run 复用)。"""
        with self._lock:
            self.run_id = ""
            self.trace_id = ""
            self.document = None
            self._current = None
            self._step_counter = 0
            self._closed_steps = ()


# ── ContextVar 暴露 current step ─────────────────────────


_lifecycle_store_var: ContextVar[StepLifecycleStore | None] = ContextVar(
    "lca_step_lifecycle_store", default=None
)


def get_lifecycle_store() -> StepLifecycleStore | None:
    """读取当前 task 的 lifecycle store。 未 bind_run → None。"""
    return _lifecycle_store_var.get()


def set_lifecycle_store(store: StepLifecycleStore) -> object:
    """设置 lifecycle store。 返回 token 给 reset。"""
    return _lifecycle_store_var.set(store)


def reset_lifecycle_store(token: object) -> None:
    _lifecycle_store_var.reset(token)  # type: ignore[arg-type]


def get_current_step() -> JournalStep | None:
    """便捷 helper —— 读当前 task 的 current step。"""
    store = get_lifecycle_store()
    if store is None:
        return None
    return store.get_current_step()


def require_current_step() -> JournalStep:
    """严格 helper —— 没 current step → RuntimeError, 防"偷偷"调用。"""
    step = get_current_step()
    if step is None:
        raise RuntimeError(
            "no open step in current task; call step_lifecycle.open_step(phase) before record_*()"
        )
    return step


# ── 顶层 facade(给调用方用) ──────────────────────────────


def open_step(
    phase: StepPhase,
    *,
    subagent_role: str | None = None,
    context: StepContext | None = None,
    parent_step_id: str | None = None,
) -> JournalStep:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError(
            "step_lifecycle.open_step: no lifecycle store bound; "
            "call set_lifecycle_store(StepLifecycleStore(...)) at runtime startup"
        )
    return store.open_step(
        phase,
        subagent_role=subagent_role,
        context=context,
        parent_step_id=parent_step_id,
    )


def record_thinking(trace: ThinkingTrace) -> None:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("record_thinking: no lifecycle store bound")
    store.record_thinking(trace)


def record_tool_call(call: ToolCallRecord) -> None:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("record_tool_call: no lifecycle store bound")
    store.record_tool_call(call)


def record_tool_result(result: ToolResult) -> None:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("record_tool_result: no lifecycle store bound")
    store.record_tool_result(result)


def record_reflect(reflect: ReflectTrace) -> None:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("record_reflect: no lifecycle store bound")
    store.record_reflect(reflect)


def record_span(span: SpanRecord) -> None:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("record_span: no lifecycle store bound")
    store.record_span(span)


def close_step(outcome: StepOutcome, *, error: str | None = None) -> JournalStep:
    store = get_lifecycle_store()
    if store is None:
        raise RuntimeError("close_step: no lifecycle store bound")
    return store.close_step(outcome, error=error)


__all__ = [
    "StepLifecycleStore",
    "close_step",
    "get_current_step",
    "get_lifecycle_store",
    "open_step",
    "record_reflect",
    "record_span",
    "record_thinking",
    "record_tool_call",
    "record_tool_result",
    "require_current_step",
    "reset_lifecycle_store",
    "set_lifecycle_store",
]
