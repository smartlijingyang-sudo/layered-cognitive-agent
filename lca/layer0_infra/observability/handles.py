"""span 句柄与导出器隔离 —— hub 的执行机制件（ADR-0037 拆分自 hub.py）。

三个内聚机制件：
- ``SpanHandle``：span 可变句柄（attributes 写入期过策略、退出落 OTel）；
- ``NullSpanHandle``：未 bind hub 时的空句柄（Null Object）；
- ``_IsolatedExporter``：导出器故障隔离包装（单后端异常不中断 run）。
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import structlog
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

if TYPE_CHECKING:
    from opentelemetry.context import Context, Token

    from lca.contracts.observability.ports import AttributePolicyBackend

_log = structlog.get_logger("lca.observability")

_ERROR_MESSAGE_MAX = 500
"""错误消息属性截断上限（避免超长堆栈撑爆 trace）。"""


class _IsolatedExporter(SpanExporter):
    """故障隔离包装：导出异常只记日志，永不向上传播。"""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    @property
    def inner(self) -> SpanExporter:
        return self._inner

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        try:
            return self._inner.export(spans)
        except Exception:
            _log.warning("span_export_failed", exporter=type(self._inner).__name__)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        try:
            self._inner.shutdown()
        except Exception:
            _log.warning("exporter_shutdown_failed", exporter=type(self._inner).__name__)

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        try:
            return self._inner.force_flush(timeout_millis)
        except Exception:
            _log.warning("exporter_flush_failed", exporter=type(self._inner).__name__)
            return False


class SpanHandle:
    """span 可变句柄：``attributes`` 字典式写入，退出时统一过策略并落 OTel。

    进入时把 span attach 到 OTel 上下文——嵌套 span/事件以此为父
    （等价于 start_as_current_span 语义）；退出时 detach。
    ``attach=False``（detached）时只计时/落属性、不占用 ambient 上下文：
    块内发射的 span/事件仍挂外层父节点（生命周期脚手架 span 用）。
    用法由包根 ``span()`` 提供，业务层不直接构造。
    """

    def __init__(
        self,
        policy: AttributePolicyBackend | None,
        otel_span: Any,
        attributes: dict[str, Any],
        *,
        attach: bool = True,
    ) -> None:
        self._policy = policy
        self._otel = otel_span
        self.attributes: dict[str, Any] = attributes
        self._attach = attach
        self._ctx_token: Token[Context] | None = None

    def __enter__(self) -> SpanHandle:
        if self._attach:
            self._ctx_token = otel_context.attach(otel_trace.set_span_in_context(self._otel))
        return self

    def mark_error(self, message: str = "") -> None:
        """显式标记 span 为错误（异常被内部捕获未传播时使用）。"""
        self._otel.set_status(StatusCode.ERROR)
        if message:
            self.attributes.setdefault("error_message", message[:_ERROR_MESSAGE_MAX])

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        del tb
        if exc is not None:
            self.attributes.setdefault("error_type", type(exc).__name__)
            self.attributes.setdefault("error_message", str(exc)[:_ERROR_MESSAGE_MAX])
            self._otel.record_exception(exc)
            self._otel.set_status(StatusCode.ERROR)
        prepared = self._policy.prepare(self.attributes) if self._policy is not None else dict(self.attributes)
        # 单次 set_attributes 比循环 set_attribute 省 N-1 次 OTel SDK 调用（评估文档 §89）
        self._otel.set_attributes(prepared)
        self._otel.end()
        if self._ctx_token is not None:
            # Token 仅在创建它的 Context 有效；跨 task 退出时静默跳过
            # （避免 OTel detach 打出 "Failed to detach context" traceback）。
            with contextlib.suppress(ValueError):
                self._ctx_token.var.reset(self._ctx_token)


class NullSpanHandle:
    """未 bind hub 时的空句柄：属性写入被安全丢弃。"""

    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def __enter__(self) -> NullSpanHandle:
        return self

    def mark_error(self, message: str = "") -> None:
        return None

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        return None
