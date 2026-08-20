"""业务层唯一可观测性发射面。

一个 ``BoundObservability`` ContextVar 持有 hub、session、actor 和 step；Journal
关联骨架仍由 ``RunScope`` 在 run 边界盖章。业务代码只有四种行为：写领域事实
``record``、写运行解释 ``observe``、开启外部追踪 ``span``、补充 span 属性
``annotate``。未绑定时全部安全 no-op。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import trace as otel_trace

from lca.contracts.atoms.telemetry import ATTR_SESSION_ID
from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus
from lca.contracts.models.observability.journal import JournalEvent, StampedEvent
from lca.layer0_infra.observability.diagnostic_operation import DiagnosticOperation
from lca.layer0_infra.observability.handles import NullSpanHandle, SpanHandle
from lca.layer0_infra.observability.hub import ObservabilityHub

_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass(frozen=True)
class BoundObservability:
    """一次运行中所有环境关联观测信息。"""

    hub: ObservabilityHub
    session_id: str | None = None
    actor_role: str = ""
    actor_step: int | None = None


_bound: ContextVar[BoundObservability | None] = ContextVar(
    "lca_observability_context", default=None
)


@dataclass(frozen=True)
class SpanContext:
    """当前 OTel span 的关联标识。"""

    trace_id: str | None
    parent_span_id: str | None


def current_hub() -> ObservabilityHub | None:
    current = _bound.get()
    return current.hub if current is not None else None


@contextmanager
def bind(hub: ObservabilityHub) -> Iterator[ObservabilityHub]:
    """在 run 边缘绑定 hub；嵌套绑定不泄漏到外层。"""
    token = _bound.set(BoundObservability(hub=hub))
    try:
        yield hub
    finally:
        _bound.reset(token)


def _replace_bound(**updates: Any) -> None:
    current = _bound.get()
    if current is not None:
        _bound.set(replace(current, **updates))


def set_actor(role: str, step: int | None) -> None:
    """更新本运行的 actor 身份。"""
    _replace_bound(actor_role=role or "", actor_step=step)


def set_session(session_id: str | None) -> None:
    """更新本运行映射到外部后端的会话标识。"""
    _replace_bound(session_id=session_id or None)


def get_span_context() -> SpanContext:
    context = otel_trace.get_current_span().get_span_context()
    if not context.is_valid:
        return SpanContext(trace_id=None, parent_span_id=None)
    return SpanContext(trace_id=format(context.trace_id, "032x"), parent_span_id=None)


def _open(name: object, attributes: dict[str, Any], *, attach: bool) -> SpanHandle | NullSpanHandle:
    current = _bound.get()
    if current is None:
        return NullSpanHandle()
    label = name.value if hasattr(name, "value") else str(name)
    attrs = dict(attributes)
    if current.session_id is not None and ATTR_SESSION_ID not in attrs:
        attrs[ATTR_SESSION_ID] = current.session_id
    return current.hub.open_span(
        label,
        attrs,
        actor_role=current.actor_role,
        actor_step=current.actor_step,
        attach=attach,
    )


def span(name: object, **attributes: Any) -> SpanHandle | NullSpanHandle:
    """开启与当前 OTel 上下文关联的 span。"""
    return _open(name, attributes, attach=True)


def detached_span(name: object, **attributes: Any) -> SpanHandle | NullSpanHandle:
    """开启不接管当前 OTel 上下文的计时 span。"""
    return _open(name, attributes, attach=False)


def event(name: object, **attributes: Any) -> None:
    """向当前 OTel trace 写入机制事件。"""
    current = _bound.get()
    if current is None:
        return
    label = name.value if hasattr(name, "value") else str(name)
    current.hub.emit_event(label, attributes)


def observe(
    category: DiagnosticCategory | str,
    operation: str,
    *,
    plugin: str = "",
    attributes: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    causation_refs: tuple[str, ...] = (),
    status: DiagnosticStatus = DiagnosticStatus.INFO,
) -> StampedEvent | None:
    """向主事件账本写入一条运行解释记录。"""
    current = _bound.get()
    if current is None:
        return None
    return current.hub.emit_diagnostic(
        category=DiagnosticCategory(category),
        operation=operation,
        plugin=plugin,
        status=status,
        attributes=attributes or {},
        output=output or {},
        causation_refs=causation_refs,
        actor_role=current.actor_role,
        actor_step=current.actor_step,
    )


def observe_operation(
    category: DiagnosticCategory | str,
    operation: str,
    *,
    plugin: str = "",
    attributes: dict[str, Any] | None = None,
    causation_refs: tuple[str, ...] = (),
) -> DiagnosticOperation:
    """为开始、成功或失败终态写入一组解释事件。"""
    return DiagnosticOperation(
        current_hub(),
        category=category,
        operation=operation,
        plugin=plugin,
        attributes=attributes or {},
        causation_refs=causation_refs,
        actor_role=lambda: _bound.get().actor_role if _bound.get() is not None else "",
        actor_step=lambda: _bound.get().actor_step if _bound.get() is not None else None,
    )


def record(event_payload: JournalEvent) -> StampedEvent | None:
    """向主事件账本追加一个已经登记的领域或生命周期事件。"""
    hub = current_hub()
    return hub.store.append(event_payload) if hub is not None else None


def annotate(**attributes: Any) -> None:
    """为当前可记录 span 写入受策略治理的属性。"""
    hub = current_hub()
    if hub is None:
        return
    current = otel_trace.get_current_span()
    if not current.is_recording():
        return
    for key, value in hub.policy.prepare(attributes).items():
        current.set_attribute(key, value)


def score(name: str, value: float, **attributes: Any) -> None:
    """向已装配的评估后端发出分数，或降级为 OTel 事件。"""
    hub = current_hub()
    if hub is not None:
        hub.score(name, value, attributes)


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


__all__ = [
    "BoundObservability",
    "SpanContext",
    "annotate",
    "bind",
    "current_hub",
    "detached_span",
    "event",
    "get_span_context",
    "observe",
    "observe_operation",
    "record",
    "score",
    "set_actor",
    "set_session",
    "span",
    "traced",
]
