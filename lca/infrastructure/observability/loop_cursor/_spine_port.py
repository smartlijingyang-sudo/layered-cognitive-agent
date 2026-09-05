"""Spine WritePort — cursor 唯一允许调用的 spine 面 + 单一写入实现。

ADR-0169 D1 / L10 定义 :class:`WritePort` 协议位;ADR-0183 PR-9 把三条
写入路径(``EventSpine.append`` / ``SpineWritePortAdapter.append`` /
cursor 直写)收口为本模块两个入口:

- :func:`spine_port_append` —— 唯一 spine 写入实现:转发给 Session runtime
  钩子,stamp / 落盘 / subscriber 派发均在钩子内完成。无钩子绑定时
  fail-loud。``EventSpine.append`` 是转发本函数的 façade。
- :func:`write_port_append` —— 唯一 WritePort 字段映射:cursor 的 6 字段
  翻译成 spine append 字段后经 façade 落盘。``SpineWritePortAdapter.append``
  是转发本函数的 façade。

ADR-0186:Session 是事件 SSOT。生产落盘经 Session observer(SpineFileSink)
写 ``<run_dir>/<run_id>.spine.jsonl``;本模块不再直接写 sink。

cursor 不得直接 import EventSpine / Serializer / Storage(ADR-0169 L4
I-PLUG1);本模块只 import spine 原语(EventRecord / EventSink /
SpineContext),不 import EventSpine 类。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextvars import ContextVar, Token
from datetime import UTC, datetime
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


# ── ADR-0185 PR-3h:Session runtime 转发缝(骨架)──────────────────────


class SessionAppendHook(Protocol):
    """Session runtime 转发钩子 — 签名与 :func:`spine_port_append` 同构。

    钩子返回 :class:`EventRecord` 即代表该次写入由 Session runtime 完整
    拥有(stamp / 落盘 / subscriber 派发均在钩子内完成);
    :func:`spine_port_append` 只转发、不重复写。
    """

    def __call__(
        self,
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
    ) -> EventRecord: ...


_session_append_hook: ContextVar[SessionAppendHook | None] = ContextVar(
    "lca_spine_session_append_hook", default=None
)


def get_session_append_hook() -> SessionAppendHook | None:
    """取当前绑定的 Session runtime 转发钩子;无则返回 ``None``。"""
    return _session_append_hook.get()


def bind_session_append_hook(hook: SessionAppendHook) -> Token[Any]:
    """绑定 Session runtime 转发钩子;返回 reset token。

    由 Session runtime 装配方调用(如 ``bind_run_event_session_from_store``)。
    未绑定时 ``spine_port_append`` 将 RuntimeError fail-loud。
    """
    return _session_append_hook.set(hook)


def reset_session_append_hook(token: Token[Any]) -> None:
    """释放 ``bind_session_append_hook`` 返回的 token。"""
    _session_append_hook.reset(token)


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
    session_hook: SessionAppendHook | None = None,
) -> EventRecord:
    """唯一 spine 写入实现(ADR-0183 PR-9, ADR-0186 Session SSOT)。

    Session runtime 钩子绑定后,全部写入转发给 Session:stamp / 落盘 /
    subscriber 派发均在钩子内完成。本函数只负责转发和 fail-loud。

    Failure 语义:
    - 无钩子绑定时 RuntimeError(fail-loud,要求调用方先绑 Session)
    - 钩子抛错时 contained(log + 返回 stub record),不传播

    ADR-0186 迁移完成后,sinks/subscribers 参数可移除(当前保留以兼容
    EventSpine.append 签名)。
    """
    hook = session_hook or get_session_append_hook()
    if hook is None:
        raise RuntimeError(
            f"spine_port_append: no Session hook bound for execution_point={execution_point!r}. "
            "Session runtime must bind hook via bind_session_append_hook() before append. "
            "See ADR-0186 for Session SSOT architecture."
        )
    try:
        return hook(
            sinks,
            subscribers,
            execution_point=execution_point,
            channel=channel,
            caller_payload=caller_payload,
            outcome=outcome,
            span_ctx=span_ctx,
            phase=phase,
            reason=reason,
            when=when,
            ref=ref,
        )
    except Exception as exc:
        if type(exc).__name__ == "I17Violation" and type(exc).__module__ in (
            "lca.plugins.observability.spine.spine_enrich",
            "lca.plugins.observability.spine.emit_pipeline",
        ):
            raise
        log.warning(
            "spine.session_forward_failed execution_point=%s err=%s",
            execution_point,
            exc,
            exc_info=True,
        )
        # Return stub record on hook failure (contained, don't kill run)
        return EventRecord(
            execution_point=execution_point,
            channel=channel,
            span_id="stub",
            parent_span_id=None,
            sequence=0,
            epoch=0,
            causality_id="stub",
            outcome=outcome,
            when=when or datetime.now(UTC),
            trace_id=None,
            when_corrected=when or datetime.now(UTC),
            prev_event_hash=None,
            run_id=SpineContext.get_run() or "default-run",
            step_id=SpineContext.get_step(),
            payload=caller_payload or {},
            phase=phase,
            reason=reason,
        )


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


__all__ = [
    "SessionAppendHook",
    "WritePort",
    "bind_session_append_hook",
    "get_session_append_hook",
    "reset_session_append_hook",
    "spine_port_append",
    "write_port_append",
]
