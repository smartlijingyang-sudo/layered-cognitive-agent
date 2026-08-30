"""OTel 容器 span 生命周期索引 —— 显式定父 + ambient attach 管理。

从 ``otel_projector`` 拆出的状态机机制件：run/delegation 容器按关联 id
索引（开/关/查父），run 容器额外 attach 进 ambient（机制平面 span 归位）。
投影器只负责事件语义分派，span 生命周期全部委托本索引。

**attach Token 与 asyncio**：``contextvars.Token`` 只能在创建它的
Context 里 ``reset``。成员经 ``asyncio.create_task`` 跑在独立 Context；
若 attach 发生在子 task、``end``/``hub.close`` 在另一 task（cancel 路径、
泄漏兜底），直接 ``otel_context.detach`` 会触发
「Token was created in a different Context」。ambient 本就 per-task 隔离，
跨 Context detach 是安全 no-op（见 ``_safe_detach``）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace

if TYPE_CHECKING:
    from opentelemetry.context import Token
    from opentelemetry.trace import Span, Tracer


def _safe_detach(token: Token) -> None:
    """在当前 Context 有效时 unwind ambient；跨 Context 则静默跳过。

    不调用 ``otel_context.detach``：其在失败时会 ``logger.exception``
    打出整段 traceback，即使异常被吞掉。直接 ``token.var.reset`` 与
    OTel ContextVarsRuntimeContext 等价，且由我们控制 ValueError。
    """
    try:
        token.var.reset(token)
    except ValueError:
        # Token 属于另一个 asyncio Context；该 Context 已结束或隔离，无需 unwind。
        return


class SpanContainerIndex:
    """容器 span 索引：关联 id → 活跃 span，含 attach token 管理。"""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._runs: dict[str, Span] = {}
        self._delegations: dict[str, Span] = {}
        self._attach_tokens: dict[str, Token] = {}
        self._own_span_ids: set[str] = set()

    @staticmethod
    def context_of(span: Span | None) -> Any:
        """span → 显式父 context（None 时为根）。"""
        return otel_trace.set_span_in_context(span) if span is not None else None

    def start(
        self,
        key: str,
        name: str,
        parent: Span | None,
        attributes: dict[str, Any],
        *,
        start_nanos: int,
        is_run: bool,
        attach: bool = False,
    ) -> Span:
        """打开容器 span（显式定父）；``attach=True`` 时同时进 ambient。"""
        span = self._tracer.start_span(
            name,
            attributes=attributes,
            context=self.context_of(parent),
            start_time=start_nanos,
        )
        self._own_span_ids.add(format(span.get_span_context().span_id, "016x"))
        (self._runs if is_run else self._delegations)[key] = span
        if attach:
            self._attach_tokens[key] = otel_context.attach(otel_trace.set_span_in_context(span))
        return span

    def end(self, key: str, attributes: dict[str, Any], *, end_nanos: int) -> None:
        """关闭容器 span（先查 run 再查 delegation），detach 对应 token。"""
        span = self._runs.pop(key, None) or self._delegations.pop(key, None)
        if span is None:
            return
        span.set_attributes(attributes)
        span.end(end_time=end_nanos)
        self.forget(span)
        token = self._attach_tokens.pop(key, None)
        if token is not None:
            _safe_detach(token)

    def run_span(self, run_id: str) -> Span | None:
        return self._runs.get(run_id)

    def delegation_span(self, delegation_id: str) -> Span | None:
        return self._delegations.get(delegation_id)

    def is_own_span(self, span: Span) -> bool:
        """是否投影器自有容器（委派混合定父判据：非自有 ambient 就近挂载）。"""
        return format(span.get_span_context().span_id, "016x") in self._own_span_ids

    def forget(self, span: Span) -> None:
        self._own_span_ids.discard(format(span.get_span_context().span_id, "016x"))

    def drain_leaked(self) -> list[Span]:
        """泄漏兜底：关闭所有未收尾容器（含 safe detach）。"""
        leaked = [*self._runs.values(), *self._delegations.values()]
        for key in (*self._runs, *self._delegations):
            token = self._attach_tokens.pop(key, None)
            if token is not None:
                _safe_detach(token)
        for span in leaked:
            self.forget(span)
        self._runs.clear()
        self._delegations.clear()
        return leaked
