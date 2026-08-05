"""Ambient 遥测引擎 —— 业务层唯一发射面（OTel 骨干的薄封装）。

规则：
- ``bind(hub)`` 只在 run 边缘调用（TeamHandle.run / CognitiveAgent.run）；
- 嵌套组件（hooks / adapters / strategies）只调用 ``span`` / ``event``；
- 未 bind 时全部调用安全 no-op（Null Object）；
- 业务层永不 import opentelemetry —— 本模块是唯一下行通道。

埋点三形态：
1. ``@traced(SpanName.X)`` —— 函数级注解，零样板；
2. ``with span(SpanName.X, ...) as h`` —— 需中途写属性的场景；
3. 零埋点 —— 认知四相 / LLM / 记忆由边界适配器自动发射。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import trace as otel_trace

from lca.contracts.telemetry import ATTR_SESSION_ID
from lca.layer0_infra.observability.hub import NullSpanHandle, ObservabilityHub, SpanHandle

_F = TypeVar("_F", bound=Callable[..., Any])

_hub_var: ContextVar[ObservabilityHub | None] = ContextVar("lca_obs_hub", default=None)
_session_var: ContextVar[str | None] = ContextVar("lca_obs_session", default=None)
_actor_role: ContextVar[str] = ContextVar("lca_obs_actor_role", default="")
_actor_step: ContextVar[int | None] = ContextVar("lca_obs_actor_step", default=None)


@dataclass(frozen=True)
class SpanContext:
    """当前 span 关联上下文（trace/span id 十六进制）。"""

    trace_id: str | None
    parent_span_id: str | None


# ── ambient 状态 ─────────────────────────────────────────


def current_hub() -> ObservabilityHub | None:
    return _hub_var.get()


@contextmanager
def bind(hub: ObservabilityHub) -> Iterator[ObservabilityHub]:
    """在 run 边缘安装 hub（可重入：嵌套 run 各自绑定）。"""
    token = _hub_var.set(hub)
    try:
        yield hub
    finally:
        _hub_var.reset(token)


def set_actor(role: str, step: int | None) -> None:
    """设置当前上下文的 actor 身份（hook 触发边界调用）。"""
    _actor_role.set(role or "")
    _actor_step.set(step)


def set_session(session_id: str | None) -> None:
    """设置会话 id（run 边缘调用；映射后端 session 视图）。"""
    _session_var.set(session_id or None)


def get_span_context() -> SpanContext:
    """当前活跃 span 的关联上下文（无活跃 span 时全 None）。"""
    ctx = otel_trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return SpanContext(trace_id=None, parent_span_id=None)
    return SpanContext(trace_id=format(ctx.trace_id, "032x"), parent_span_id=None)


# ── 发射 API ─────────────────────────────────────────────


def span(name: object, **attributes: Any) -> SpanHandle | NullSpanHandle:
    """打开子 span（context manager）。

    ``name`` 必须取 ``SpanName`` 成员（守卫测试强制）；
    会话 id 自动注入根级属性。
    """
    hub = _hub_var.get()
    if hub is None:
        return NullSpanHandle()
    label = name.value if hasattr(name, "value") else str(name)
    attrs = dict(attributes)
    session = _session_var.get()
    if session is not None and ATTR_SESSION_ID not in attrs:
        attrs[ATTR_SESSION_ID] = session
    return hub.open_span(label, attrs, actor_role=_actor_role.get(), actor_step=_actor_step.get())


def event(name: object, **attributes: Any) -> None:
    """记录业务事件（EventName 成员）。"""
    hub = _hub_var.get()
    if hub is None:
        return
    label = name.value if hasattr(name, "value") else str(name)
    hub.emit_event(label, attributes)


def annotate(**attributes: Any) -> None:
    """给当前活跃 span 追加属性（如 think 相位挂 prompt 模板名）。

    属性经策略脱敏/截断；无活跃 span 时安全忽略。
    """
    hub = _hub_var.get()
    if hub is None:
        return
    current = otel_trace.get_current_span()
    if not current.is_recording():
        return
    for key, value in hub.policy.prepare(attributes).items():
        current.set_attribute(key, value)


def score(name: str, value: float, **attributes: Any) -> None:
    """评估打分（后端支持则记 score，否则降级事件）。"""
    hub = _hub_var.get()
    if hub is None:
        return
    hub.score(name, value, attributes)


# ── 装饰器形态 ───────────────────────────────────────────


def traced(
    name: object, *, capture: Callable[..., dict[str, Any]] | None = None
) -> Callable[[_F], _F]:
    """函数级埋点装饰器：计时 / 异常 / 落 span 全自动。

    ``capture`` 为纯函数，接收与被装饰函数相同的参数，返回属性字典
    （写入前经属性策略脱敏/截断）。同步与异步函数均支持。
    """
    label = name.value if hasattr(name, "value") else str(name)

    def _capture_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
        return capture(*args, **kwargs) if capture is not None else {}

    def decorator(fn: _F) -> _F:
        import inspect

        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with span(label, **_capture_args(args, kwargs)):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(label, **_capture_args(args, kwargs)):
                return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
