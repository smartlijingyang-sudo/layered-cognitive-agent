"""Spine WritePort — cursor 唯一允许调用的 spine 面 + 单一写入实现。

ADR-0169 D1 / L10 定义 :class:`WritePort` 协议位;ADR-0183 PR-9 把三条
写入路径(``EventSpine.append`` / ``SpineWritePortAdapter.append`` /
cursor 直写)收口为本模块两个入口:

- :func:`spine_port_append` —— 唯一 spine 写入实现:stamp(seq / epoch /
  causality / hash chain)→ sinks(FD-1 fail-fast)→ subscribers(FD-2
  容错)。``EventSpine.append`` 是转发本函数的 façade。
- :func:`write_port_append` —— 唯一 WritePort 字段映射:cursor 的 6 字段
  翻译成 spine append 字段后经 façade 落盘。``SpineWritePortAdapter.append``
  是转发本函数的 façade。

生产落盘行为不变:sinks = [FileSink],写 ``<run_dir>/<run_id>.spine.jsonl``。
cursor 不得直接 import EventSpine / Serializer / Storage(ADR-0169 L4
I-PLUG1);本模块只 import spine 原语(EventRecord / EventSink /
SpineContext),不 import EventSpine 类。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.spine.sinks.base import EventSink

log = logging.getLogger(__name__)


class WritePort(Protocol):
    """append-only 语义写入;返回分配的 seq。"""

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int: ...


def spine_port_append(
    sinks: Sequence[EventSink],
    subscribers: Sequence[Callable[[EventRecord], None]],
    *,
    execution_point: str,
    channel: Channel,
    caller_payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
    span_ctx: Any | None = None,
    phase: Phase = "live",
    reason: str | None = None,
    when: datetime | None = None,
    ref: Any = None,
) -> EventRecord:
    """唯一 spine 写入实现(ADR-0183 PR-9)。

    Stamp(seq / epoch / span / causality_id / hash chain,全部由
    :class:`SpineContext` 主导分配)→ 写全部 sinks → 更新 hash chain →
    通知 subscribers。

    Failure 语义(与原 EventSpine.append 一致):
    - FD-1 sink 错误 fail-fast,首个错误向调用方传播;
    - FD-2 subscriber 错误容错,仅日志 ``spine.deriver_failed``,不传播;
      原事件仍到达 sink。

    所有权:record 为新建 frozen 实例,sinks / subscribers 只读遍历。
    """
    now = when or datetime.now(timezone.utc)
    seq = SpineContext.next_sequence()
    epoch = SpineContext.next_epoch()
    current_span = SpineContext.current_span()
    parent_id = (
        span_ctx.parent_span_id
        if span_ctx is not None
        else (current_span.span_id if current_span is not None else None)
    )
    span_id = span_ctx.span_id if span_ctx is not None else f"lca-seq-{seq:08x}"
    run_id = SpineContext.get_run() or "default-run"
    step_id = SpineContext.get_step()
    prev_hash = SpineContext.last_hash()
    causality_payload = json.dumps(
        {
            "execution_point": execution_point,
            "channel": channel,
            "payload": caller_payload or {},
            "span_id": span_id,
            "epoch": epoch,
        },
        sort_keys=True,
        default=str,
    )
    causality_id = "sha256:" + hashlib.sha256(causality_payload.encode()).hexdigest()
    new_hash = (
        "sha256:" + hashlib.sha256(((prev_hash or "") + causality_id).encode("utf-8")).hexdigest()
    )

    # trace_id 解析链(ADR-0183 §3.9 PR-12):
    # 1) EventBus.publish 显式 trace_id → 经 ref 传入(ref 优先)
    # 2) caller_payload["trace_id"] 字段(老路径兼容)
    # 3) SpineContext contextvars(_trace_id,EventBus 默认注入)
    # 4) 全 None(无 trace 关联)
    _ref_trace_id = getattr(ref, "trace_id", None) if ref is not None else None
    _payload_trace_id = (caller_payload or {}).get("trace_id")
    if _ref_trace_id is not None:
        _resolved_trace_id: str | None = _ref_trace_id
    elif _payload_trace_id is not None:
        _resolved_trace_id = str(_payload_trace_id)
    else:
        _resolved_trace_id = SpineContext.get_trace_id()

    record = EventRecord(
        execution_point=execution_point,
        channel=channel,
        span_id=span_id,
        parent_span_id=parent_id,
        sequence=seq,
        epoch=epoch,
        causality_id=causality_id,
        outcome=outcome,
        when=now,
        # trace_id 由 EventBus.publish 经 ref 注入(ADR-0183 §3.9 PR-12);
        # 老路径走 SpineContext contextvars 兜底,保持向后兼容。
        trace_id=_resolved_trace_id,
        when_corrected=now,
        prev_event_hash=prev_hash,
        run_id=run_id,
        step_id=step_id,
        payload=caller_payload or {},
        phase=phase,
        reason=reason,
    )

    # FD-1: sinks fail-fast; first error propagates
    for sink in sinks:
        sink.write(record)

    SpineContext.chain_hash(new_hash)

    # FD-2: subscribers contained; failures logged, never propagated
    for fn in tuple(subscribers):
        try:
            fn(record)
        except Exception as exc:
            log.warning(
                "spine.deriver_failed execution_point=%s deriver=%s err=%s",
                record.execution_point,
                getattr(fn, "__qualname__", repr(fn)),
                exc,
                exc_info=True,
            )

    return record


def write_port_append(
    spine: Any,
    *,
    execution_point: str,
    payload: dict[str, Any],
    run_id: str,
    seq: int,
    incarnation: int,
    phase: str | None,
) -> int:
    """唯一 WritePort 字段映射(ADR-0183 PR-9)— cursor 写入的单一入口。

    WritePort 6 字段 → spine append 字段:

    - ``run_id`` 写入 :class:`SpineContext`(spine append 内部经
      ``SpineContext.get_run`` 关联当前 run);
    - ``incarnation`` 进 payload(ADR-0169 L14 envelope);
    - cursor 给的 ``seq`` / ``run_id`` 仅透传,真实 seq / run_id 由
      :class:`SpineContext` 主导分配,故返回传入的 ``seq`` 以满足
      WritePort 语义(SSOT 不漂)。

    ``spine`` 为 duck-type spine 句柄(任何带 ``append(...)`` 的对象,
    生产为 :class:`EventSpine`);实际落盘经 ``EventSpine.append`` façade →
    :func:`spine_port_append` → FileSink(``<run_id>.spine.jsonl``)。
    """
    SpineContext.set_run(run_id)
    merged_payload = {**payload, "incarnation": incarnation}
    spine.append(
        execution_point=execution_point,
        caller_payload=merged_payload,
        channel="fact",
        outcome=None,
        span_ctx=None,
        phase="live" if phase is None else str(phase),
        reason=None,
        when=None,
    )
    return seq


# ── ADR-0184 PR-2:spine_port_append_async + EventSpine.append_async 兼容 shim ──


async def spine_port_append_async(
    sinks: Sequence[EventSink],
    subscribers: Sequence[Callable[[EventRecord], None]],
    *,
    execution_point: str,
    channel: Channel,
    caller_payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
    span_ctx: Any | None = None,
    phase: Phase = "live",
    reason: str | None = None,
    when: datetime | None = None,
    ref: Any = None,
) -> EventRecord:
    """spine_port_append 异步版 — ADR-0184 PR-2 入口,走 EnvelopeBus + PersistenceWorker。

    同步版 :func:`spine_port_append` 仍走 FileSink 直写(SSR 兼容 shim);异步版
    经 :class:`lca_kernel.events.bus.EventBus.publish_async` 入队 + 等 worker
    落盘,构造 :class:`lca.infrastructure.observability.spine.event_record.EventRecord`
    返回给 caller(供老 subscribers 链收尾)。

    ``subscribers`` 仍按原顺序同步调(callback 失败 contained 吞错);这是与
    老路径的唯一同步钩子,可让 :class:`step_tree_accumulator_step_tree_accumulator` 一类
    deriver 收到事件后做模型可见状态。
    """
    from lca.contracts.event import Category
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.payloads import SpineEventPayload
    from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY
    from lca_kernel.events.spine_runtime import build_record

    cat_str = _SPINE_EP_TO_CATEGORY.get(execution_point)
    if cat_str is None:
        raise ValueError(f"spine EP {execution_point!r} 未登记 category 映射(ADR-0181 后续 PR 补)")

    payload = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=str(channel),
        payload=caller_payload or {},
    )

    # 调 EnvelopeBus.publish_async → super().publish 入队 → worker.flush_for 落盘。
    # producer 用 spine_reflector_cognition 的 marker 类(已在注册表)通过鉴权。
    # 生产 plugin 主体仍走老 sync :func:`spine_port_append` 直写;本 async 入口
    # 是 PR-3 迁入准备。
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    event_ref = await EventBus.default().publish_async(payload, producer=ReflectorClass)

    # 同老路径:构造 EventRecord 给老 subscribers 同步回调(供 deriver)。
    record = build_record(payload, event_ref)
    for fn in subscribers:
        try:
            fn(record)
        except Exception:
            log.warning(
                "spine.deriver_failed (async path) execution_point=%s deriver=%s",
                record.execution_point,
                getattr(fn, "__qualname__", repr(fn)),
                exc_info=True,
            )

    return record


def write_port_append_async(
    spine: Any,
    *,
    execution_point: str,
    payload: dict[str, Any],
    run_id: str,
    seq: int,
    incarnation: int,
    phase: str | None,
) -> int:
    """WritePort 异步版本(ADR-0184 PR-2 shim)。

    生产路径仍走老 :func:`write_port_append`;本函数保留作为新入口,
    仅当 spine 句柄支持 ``append_async`` 时被驱动,否则退回老路径。

    # COMPAT(delete-when: PR-3 把 cursor 完全迁到 EventBus.publish_async,
    # tracking: ADR-0184 PR-2)
    """
    if not hasattr(spine, "append_async"):
        return write_port_append(
            spine,
            execution_point=execution_point,
            payload=payload,
            run_id=run_id,
            seq=seq,
            incarnation=incarnation,
            phase=phase,
        )
    SpineContext.set_run(run_id)
    merged_payload = {**payload, "incarnation": incarnation}
    return spine.append_async(
        execution_point=execution_point,
        caller_payload=merged_payload,
        channel="fact",
        outcome=None,
        span_ctx=None,
        phase="live" if phase is None else str(phase),
        reason=None,
        when=None,
    )


__all__ = [
    "WritePort",
    "spine_port_append",
    "spine_port_append_async",
    "write_port_append",
    "write_port_append_async",
]
