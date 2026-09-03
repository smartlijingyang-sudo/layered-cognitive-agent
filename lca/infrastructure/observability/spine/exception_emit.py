"""异常事件唯一 emitter —— 任何路径任何时机的异常都走这里。

ADR-0169 + ADR-2026-09-02-i17-stream-align §B: SSOT 异常归一化
(:class:`lca.contracts.observability.exception_capture.ExceptionRecord`)
产生后,**只能** 通过 :func:`emit_exception_caught` 落 spine event。

历史上 ``transport_emit.emit_carrier_exception_caught`` 是个残废实现
—— payload 只带 ``exc_type / message`` 不带 traceback,FileSink 不触发
offload,sidecar 永远不出现;同时装饰器路径 (``instrument_wrap``) 直接
手搓 dict,字段不一致、size 不一致、落到不同 sink。两套归一化路径并存
是历史回归的根因。

这条 module 是唯一 emitter:接收 ``ExceptionRecord``,序列化 payload,
统一走 ``error`` channel + ``failure`` outcome。FileSink 收到 size > 4 KiB
的 payload 时自动 offload 到 ``<sha256>.json`` sidecar,这是 FileSink 的
本职 —— 本文件不关心 sidecar 是否落盘,只关心"event 完整"。
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.observability import ExceptionRecord as ExceptionRecordT
from lca.harness.declarative.compile.instrument_wrap import resolve_active_spine
from lca.infrastructure.observability.spine.event_record import EventRecord

_EXECUTION_POINT = "exception.caught"
_CHANNEL_ERROR: Literal["error"] = "error"
_OUTCOME_FAILURE: Literal["failure"] = "failure"


def _safe_append(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any] | None = None,
    outcome: str | None = None,
) -> EventRecord | None:
    """Append a spine event via the process-local accessor。

    内联自 transport_emit（PR-4 与 transport_emit 一起退役）；语义未变。
    spine is None → None；wire 后 fail-loud。
    """
    spine = resolve_active_spine()
    if spine is None:
        return None
    return spine.append(
        execution_point=execution_point,
        channel=channel,
        caller_payload=payload,
        outcome=outcome,
    )


def emit_exception_caught(record: ExceptionRecordT) -> EventRecord | None:
    """异常捕获事件的唯一 emitter(SSOT)。

    接收 :class:`ExceptionRecord`,通过 ``record.asdict()`` 序列化
    payload,统一走 ``error`` channel + ``failure`` outcome。

    任何 caller 必须先把 ``BaseException`` 经
    :func:`lca.contracts.observability.exc_to_record` 归一化,再调用
    本函数。**禁止直接构造 dict payload 走其它 emitter**(包括
    已删除的 ``emit_carrier_exception_caught``)。
    """
    return _safe_append(
        execution_point=_EXECUTION_POINT,
        channel=_CHANNEL_ERROR,
        payload=record.asdict(),
        outcome=_OUTCOME_FAILURE,
    )


__all__ = ["emit_exception_caught"]
