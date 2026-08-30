"""OtelTracer —— 默认 TracerBackend（OpenTelemetry SDK 直接封装）。

业务层 ``span(name)`` → OtelTracer.start(name) → ``SpanHandle`` context manager。
OTel SDK 本身就是 plugin abstraction（TracerProvider 接受任意 SpanExporter），
不需要再包一层。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from lca.contracts.observability.ports import AttributePolicyBackend, TracerBackend
from lca.layer0_infra.observability.handles import NullSpanHandle, SpanHandle
from lca.layer0_infra.observability.policy import otel_safe_attributes

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


class OtelTracer(TracerBackend):
    """OTel SDK 的薄封装：start span + 返回 SpanHandle context manager。"""

    def __init__(
        self,
        tracer: Tracer | None,
        *,
        policy: AttributePolicyBackend | None = None,
    ) -> None:
        self._tracer = tracer
        self._policy = policy

    @contextmanager
    def start(self, name: str, **attrs: Any) -> Iterator[Any]:
        if self._tracer is None:
            # 未绑定时安全 no-op（Null Object 模式）
            with NullSpanHandle() as h:
                yield h
            return
        # 走 policy 准备属性；无 policy 时原样透传
        prepared = self._policy.prepare(attrs) if self._policy is not None else dict(attrs)
        otel_span = self._tracer.start_span(name, attributes=otel_safe_attributes(prepared))
        handle = SpanHandle(self._policy, otel_span, dict(attrs), attach=True)
        with handle as h:
            yield h


__all__ = ["OtelTracer"]
