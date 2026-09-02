"""可观测性 dispatch 入口 —— 80 行内。

业务层只看到 4 个动词（record / span / annotate / score）和 1 个 scope 上下文
（RunContext + bind + set_actor + set_session）。Backend 实例由 ``BoundObservability``
持有遥测引用（journal / tracer / policy / scorers）以及兼容的证据字段；证据消费者通过 EvidenceBinding 接缝读取。

任何 backend 的实现细节都在 plugin 里；facade 只做"拿 ContextVar → 转发"。
新增 backend = 新增 plugin；换 backend = 改 settings；不改 facade。

不再有的概念：
- ``ObservabilityHub`` 8 字段 god object（已删除）
- ``BackendBridge`` / ``ScorerFn`` Protocol（adapter 各自持有 client）
- ``DiagnosticSink`` / ``JsonlDiagnosticSink`` / ``DiagnosticJsonlProjection``（诊断是 journal 一类事件）
- ``event()``（死代码 + 与 JournalEvent 撞名）
- ``observe()`` / ``observe_operation()``（改名 ``record_runtime`` / ``record_operation``）
- ``EXPORTER_FACTORIES`` / ``JOURNAL_PROJECTOR_FACTORIES`` 模块级 dict（改 seam 注册表）
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

import structlog
from opentelemetry import trace as otel_trace

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.atoms.telemetry import ATTR_SESSION_ID
from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal import (
    JournalEvent,
    RuntimeObserved,
    StampedEvent,
)
from lca.contracts.models.observability.journal_step import (
    ReflectTrace,
    SpanRecord,
    StepContext,
    StepPhase,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.models.observability.journal_step import (
    StepOutcome as StepLifecycleOutcome,
)
from lca.contracts.observability.evidence import (
    EvidencePolicy,
    EvidenceStore,
)
from lca.contracts.observability.ports import (
    AttributePolicyBackend,
    JournalBackend,
    ScorerFn,
    TracerBackend,
)

_F = TypeVar("_F", bound=Callable[..., Any])


# ── Scope 上下文：唯一 ambient ─────────────────────────────────
# 业务代码的"我是谁"——trace / run / actor / session。所有 backend 共享同一份
# scope，由 runtime 边界（bind/run_scope）统一设置；facade 不感知具体 backend。
@dataclass(frozen=True)
class RunContext:
    trace_id: TraceId = ""
    run_id: RunId = ""
    parent_run_id: RunId | None = None
    agent_role: str = ""
    step: int = 0
    session_id: str | None = None


_run_context: ContextVar[RunContext | None] = ContextVar("lca_run_context", default=None)


def _current_run_context_or_empty() -> RunContext:
    return _run_context.get() or RunContext()


def current_context() -> RunContext | None:
    return _run_context.get()


@contextmanager
def bind(ctx: RunContext) -> Iterator[RunContext]:
    """在 run 边缘绑定 scope；嵌套绑定不泄漏到外层。"""
    token = _run_context.set(ctx)
    try:
        yield ctx
    finally:
        _run_context.reset(token)


def set_actor(role: str, step: int | None) -> None:
    current = _current_run_context_or_empty()
    _run_context.set(replace(current, agent_role=role or "", step=step or 0))


def set_session(session_id: str | None) -> None:
    current = _current_run_context_or_empty()
    _run_context.set(replace(current, session_id=session_id or None))


# ── 当前 run 激活的 backend 引用集 ───────────────────────────────
# 遥测（journal/tracer/policy/scorers）与证据（store/policy）拥有不同的
# 生命周期和替换理由。EvidenceBinding 把证据的成对依赖收口成一个接缝，
# 避免消费者自行判断两个字段是否匹配；BoundObservability 仍保留旧字段
# 作为兼容输入，新的消费者应通过 evidence_binding() 读取。
@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    """当前 run 的证据存储与治理策略。"""

    store: EvidenceStore | None = None
    policy: EvidencePolicy | None = None


@dataclass(frozen=True)
class BoundObservability:
    journal: JournalBackend | None = None
    tracer: TracerBackend | None = None
    policy: AttributePolicyBackend | None = None
    scorers: tuple[ScorerFn, ...] = ()
    evidence_store: EvidenceStore | None = None
    evidence_policy: EvidencePolicy | None = None

    def evidence_binding(self) -> EvidenceBinding:
        """Return the evidence seam as one coherent dependency pair."""
        return EvidenceBinding(store=self.evidence_store, policy=self.evidence_policy)

    def with_journal_projection(self, projection: Any) -> BoundObservability:
        """返回追加 run-scoped journal projection 后的新 BoundObservability。

        Journal backend 必须实现 ``with_projection``（immutable 风格）；不存在
        时返回自身。Boot 期构造的基线 ``BoundObservability`` 持有共享 readers，
        run 边追加 jsonl/tail/process_journal 等 writer，不破坏原基线。
        """
        if self.journal is None:
            return self
        append = getattr(self.journal, "with_projection", None)
        if not callable(append):
            return self
        return replace(self, journal=append(projection))

    def flush(self) -> None:
        """冲刷所有 backend 缓冲。"""
        if self.journal is not None:
            self.journal.flush()

    def close(self) -> None:
        """冲刷并关闭所有 backend。"""
        self.flush()
        if self.journal is not None:
            self.journal.close()


_bound: ContextVar[BoundObservability | None] = ContextVar("lca_observability_bound", default=None)


def current_bound() -> BoundObservability | None:
    return _bound.get()


@contextmanager
def bind_backends(bound: BoundObservability) -> Iterator[BoundObservability]:
    """在 run 边缘激活 backend；嵌套绑定不泄漏到外层。"""
    token = _bound.set(bound)
    try:
        yield bound
    finally:
        _bound.reset(token)


# ── 4 个 dispatch 入口：record / span / annotate / score ─────────────


def record(event: JournalEvent) -> StampedEvent | None:
    """向当前 journal 写入领域/运行时事实。"""
    bound = _bound.get()
    if bound is None or bound.journal is None:
        return None
    return bound.journal.write(event)


@contextmanager
def span(name: object, **attributes: Any) -> Iterator[Any]:
    """开启当前 tracer 的 span。"""
    bound = _bound.get()
    if bound is None or bound.tracer is None:
        # 无 tracer 时 no-op；callers 拿到的可能是 NullSpanHandle
        from lca.infrastructure.observability.adapters.handles import NullSpanHandle

        with NullSpanHandle() as h:
            yield h
        return
    label = name.value if hasattr(name, "value") else str(name)
    with bound.tracer.start(label, **attributes) as h:
        # 自动写入 session_id（如果当前 context 有）
        ctx = _current_run_context_or_empty()
        if ctx.session_id and ATTR_SESSION_ID not in h.attributes:
            h.attributes[ATTR_SESSION_ID] = ctx.session_id
        yield h


@contextmanager
def detached_span(name: object, **attributes: Any) -> Iterator[Any]:
    """开启不接管 ambient 的计时 span（用于生命周期脚手架）。"""
    bound = _bound.get()
    if bound is None or bound.tracer is None:
        from lca.infrastructure.observability.adapters.handles import NullSpanHandle

        with NullSpanHandle() as h:
            yield h
        return
    # detached 在 tracer 层通过 attach=False 表达；当前 OTelTracer 默认 attach=True
    # 简化：detached 等同普通 span；OtelTracer 后续 PR 加 attach 参数
    label = name.value if hasattr(name, "value") else str(name)
    with bound.tracer.start(label, **attributes) as h:
        yield h


def annotate(**attributes: Any) -> None:
    """给当前 OTel span 加属性（走 policy 脱敏/截断）。"""
    bound = _bound.get()
    if bound is None or bound.policy is None:
        return
    current = otel_trace.get_current_span()
    if not current.is_recording():
        return
    prepared = bound.policy.prepare(attributes)
    for key, value in prepared.items():
        current.set_attribute(key, value)


def score(name: str, value: float, **attributes: Any) -> None:
    """调用所有激活的 scorer；任一失败不影响其他。"""
    bound = _bound.get()
    if bound is None or not bound.scorers:
        return
    attrs = dict(attributes)
    for scorer in bound.scorers:
        try:
            scorer(name, value, attrs)
        except Exception:
            _log.warning("scorer_failed", scorer=getattr(scorer, "__name__", str(scorer)))


# ── record_runtime / record_operation：语义化运行时事件 ─────────────

_KIND_BY_CATEGORY: dict[DiagnosticCategory, RuntimeKind] = {
    DiagnosticCategory.AGENT: RuntimeKind.AGENT,
    DiagnosticCategory.PLUGIN: RuntimeKind.PLUGIN,
    DiagnosticCategory.HOOK: RuntimeKind.HOOK,
    DiagnosticCategory.LLM: RuntimeKind.LLM,
    DiagnosticCategory.TOOL: RuntimeKind.TOOL,
    DiagnosticCategory.MEMORY: RuntimeKind.MEMORY,
    DiagnosticCategory.TRANSPORT: RuntimeKind.TRANSPORT,
    DiagnosticCategory.INFRA: RuntimeKind.PLUGIN,
    DiagnosticCategory.JOURNAL: RuntimeKind.PLUGIN,
}

_DEFAULT_KIND = RuntimeKind.PLUGIN
"""未知 DiagnosticCategory 的兜底 kind；保证 record_runtime 不抛 KeyError。"""

_OUTCOME_BY_STATUS: dict[DiagnosticStatus, OperationOutcome] = {
    DiagnosticStatus.INFO: OperationOutcome.OK,
    DiagnosticStatus.STARTED: OperationOutcome.STARTED,
    DiagnosticStatus.SUCCEEDED: OperationOutcome.OK,
    DiagnosticStatus.FAILED: OperationOutcome.ERROR,
}


def record_runtime(
    category: DiagnosticCategory | str,
    operation: str,
    *,
    plugin: str = "",
    attributes: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    causation_refs: tuple[str, ...] = (),
    status: DiagnosticStatus = DiagnosticStatus.INFO,
) -> StampedEvent | None:
    """向 journal 写入一条 ``RuntimeObserved`` 记录。"""
    ctx = _current_run_context_or_empty()
    refs = tuple(
        int(ref.removeprefix("journal:"))
        for ref in causation_refs
        if ref.removeprefix("journal:").isdigit()
    )
    if isinstance(category, DiagnosticCategory):
        kind = _KIND_BY_CATEGORY.get(category, _DEFAULT_KIND)
    else:
        try:
            kind = _KIND_BY_CATEGORY[DiagnosticCategory(category)]
        except (KeyError, ValueError):
            kind = _DEFAULT_KIND
    return record(
        RuntimeObserved(
            kind=kind,
            operation=operation,
            source=plugin or ctx.agent_role or "runtime",
            outcome=_OUTCOME_BY_STATUS[status],
            duration_ms=None,
            attributes={"actor_role": ctx.agent_role, "actor_step": ctx.step, **(attributes or {})},
            output=output or {},
            error_code="",
            error_message="",
            causation_refs=refs,
        )
    )


class OperationRecorder:
    """``record_operation()`` 返回的上下文管理器；进入/退出各写一条 RuntimeObserved。"""

    def __init__(
        self,
        category: DiagnosticCategory | str,
        operation: str,
        *,
        plugin: str = "",
        attributes: dict[str, Any] | None = None,
        causation_refs: tuple[str, ...] = (),
    ) -> None:
        self._category = category
        self._operation = operation
        self._plugin = plugin
        self._attributes = attributes or {}
        self._causation_refs = causation_refs
        self._output: dict[str, Any] = {}
        self._started = 0.0

    def set_output(self, **output: Any) -> None:
        self._output.update(output)

    def __enter__(self) -> OperationRecorder:
        self._started = time.perf_counter()
        record_runtime(
            self._category,
            self._operation,
            plugin=self._plugin,
            attributes=self._attributes,
            output=self._output,
            causation_refs=self._causation_refs,
            status=DiagnosticStatus.STARTED,
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: Any,
    ) -> bool:
        duration_ms = int((time.perf_counter() - self._started) * 1000) if self._started else 0
        output = {**self._output, "duration_ms": duration_ms}
        if exc is None:
            record_runtime(
                self._category,
                self._operation,
                plugin=self._plugin,
                attributes=self._attributes,
                output=output,
                causation_refs=self._causation_refs,
                status=DiagnosticStatus.SUCCEEDED,
            )
        else:
            record_runtime(
                self._category,
                self._operation,
                plugin=self._plugin,
                attributes={
                    **self._attributes,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                output=output,
                causation_refs=self._causation_refs,
                status=DiagnosticStatus.FAILED,
            )
        return False  # 异常不吞


@contextmanager
def record_operation(
    category: DiagnosticCategory | str,
    operation: str,
    *,
    plugin: str = "",
    attributes: dict[str, Any] | None = None,
    causation_refs: tuple[str, ...] = (),
) -> Iterator[OperationRecorder]:
    """开启一次运行操作的 STARTED/SUCCEEDED|FAILED 生命周期记录。"""
    rec = OperationRecorder(
        category=category,
        operation=operation,
        plugin=plugin,
        attributes=attributes,
        causation_refs=causation_refs,
    )
    with rec:
        yield rec


# ── 装饰器 ─────────────────────────────────────────────


def traced(
    name: object, *, capture: Callable[..., dict[str, Any]] | None = None
) -> Callable[[_F], _F]:
    """用 span 包裹同步或异步函数。"""
    label = name.value if hasattr(name, "value") else str(name)

    def decorator(fn: _F) -> _F:
        import inspect

        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                attrs = capture(*args, **kwargs) if capture is not None else {}
                with span(label, **attrs):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            attrs = capture(*args, **kwargs) if capture is not None else {}
            with span(label, **attrs):
                return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ── Span context（get current OTel span info） ──────────────


@dataclass(frozen=True)
class SpanContextInfo:
    trace_id: str | None
    parent_span_id: str | None


def get_span_context() -> SpanContextInfo:
    context = otel_trace.get_current_span().get_span_context()
    if not context.is_valid:
        return SpanContextInfo(trace_id=None, parent_span_id=None)
    return SpanContextInfo(trace_id=format(context.trace_id, "032x"), parent_span_id=None)


# ── structured logger ────────────────────────────────────

_log = structlog.get_logger("lca.observability")


# ── Step-tree API(ADR-0167 D11: facade 转发给当前 StepCoordinator) ───
#
# 设计: facade 不持有 step 状态, 转发给绑定的 StepCoordinator。 唯一区别是
# facade 额外检查 _run_context 是否绑定(防御: 不绑 context 就没有当前 run
# 身份, 写没意义)。 Phase 3 之后 facade 唯一的"step"入口就是 begin_step /
# record_* / end_step, 全部走 StepCoordinator → writable_matrix 五面矩阵
# → events.jsonl → StepTreeAccumulatorDeriver → journal.json (ADR-0167
# I-MV3: Replay ≡ finalize)。
#
# **延迟 import**: writable_matrix 在 infrastructure 包, facade 在同包内,
# 但 facade 不在 infrastructure 内部 import 路径上, 仍用延迟 import 防循环。
# 副作用: 调用方必须先 bind StepCoordinator (transport 在 prepare 阶段 bind),
# 否则抛 RuntimeError; 不允许无 run 静默 no-op(违反 ADR-0167 D13 B2)。
#
# 迁移说明: 原 StepLifecycleStore / step_lifecycle 路径已删除(ADR-0167 PR-3),
# 本节 facade 即唯一 step 入口。


def _require_run_bound() -> RunContext:
    """step API 要求 context 已 bind(否则不知道当前 run)。"""
    ctx = _run_context.get()
    if ctx is None:
        raise RuntimeError(
            "step API requires bound run context; "
            "call facade.bind(RunContext(run_id=..., trace_id=...)) first"
        )
    return ctx


def _require_coordinator() -> StepCoordinator:
    """step API 要求已 bind StepCoordinator(transport 在 prepare 阶段绑)。

    失败时抛 RuntimeError 而不是返回 None —— ADR-0167 D13 B2 禁伪防御:
    无 coordinator 时 step API 不能静默 no-op。
    """
    from lca.infrastructure.observability.writable_matrix.coordinator import (
        get_current_coordinator,
    )

    coord = get_current_coordinator()
    if coord is None:
        raise RuntimeError(
            "step API requires bound StepCoordinator; "
            "transport must bind coordinator in RunExecutionEnvironment.prepare"
        )
    return coord


def step_open(
    phase: StepPhase,
    *,
    subagent_role: str | None = None,
    context: StepContext | None = None,
    parent_step_id: str | None = None,
) -> str:
    """开 step(走 StepCoordinator.begin_step)。"""
    _require_run_bound()
    coord = _require_coordinator()
    ctx_kw: dict[str, Any] = {}
    if context is not None:
        ctx_kw["context"] = context
    return coord.begin_step(
        str(phase),
        subagent_role=subagent_role,
        parent_step_id=parent_step_id,
        **ctx_kw,
    )


def step_record_thinking(trace: ThinkingTrace) -> None:
    """思考 → StepCoordinator.record_thinking → spine EP ``step.thinking.record``。"""
    _require_run_bound()
    _require_coordinator().record_thinking(trace)


def step_record_tool_call(call: ToolCallRecord) -> None:
    """工具调用 → spine EP ``step.tool_call.record``。"""
    _require_run_bound()
    _require_coordinator().record_tool_call(call)


def step_record_tool_result(result: ToolResult) -> None:
    """工具结果 → spine EP ``step.tool_result.record``(outcome 跟 ok 字段)。"""
    _require_run_bound()
    _require_coordinator().record_tool_result(result)


def step_record_reflect(reflect: ReflectTrace) -> None:
    """反思 → spine EP ``step.reflect.record``。"""
    _require_run_bound()
    _require_coordinator().record_reflect(reflect)


def step_record_span(span: SpanRecord) -> None:
    """折叠诊断 → spine EP ``step.span.record``(RuntimeObserved / ToolRetryProgress / ContextCompacted)。"""
    _require_run_bound()
    _require_coordinator().record_span(span)


def step_close(
    outcome: StepLifecycleOutcome,
    *,
    error: str | None = None,
) -> None:
    """闭 step(走 StepCoordinator.end_step)。"""
    _require_run_bound()
    return _require_coordinator().end_step(str(outcome), error=error)


__all__ = [
    "BoundObservability",
    "EvidenceBinding",
    "OperationRecorder",
    "RunContext",
    "SpanContextInfo",
    "annotate",
    "bind",
    "bind_backends",
    "current_bound",
    "current_context",
    "detached_span",
    "get_span_context",
    "record",
    "record_operation",
    "record_runtime",
    "score",
    "set_actor",
    "set_session",
    "span",
    "step_close",
    "step_open",
    "step_record_reflect",
    "step_record_span",
    "step_record_thinking",
    "step_record_tool_call",
    "step_record_tool_result",
    "traced",
]


if TYPE_CHECKING:
    # 仅类型检查时引入;运行时通过 ``_require_coordinator()`` duck-type
    # 访问 record_*,避免 facade ↔ writable_matrix 循环 import。
    from lca.infrastructure.observability.writable_matrix.coordinator import (
        StepCoordinator,
    )
