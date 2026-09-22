"""G0 单一事实生产门面(ADR-0194 §3.1)。

所有 durable 事实经本门面统一走 ``Session.append``;spine EP 在 hook 未激活时经本模块内聚的
enrich seam 合并 FieldProducer 字段(与 Session hook 同轨)。catalog / surface 事实委托
``harness.session.emit`` 或 raw ``Session.append``;spine EP 经 publish seam 保留 typed payload。
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, cast

import structlog

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, FactGateway
from lca.contracts.protocols.loop.spine_publish import (
    get_active_field_producers,
    get_active_spine_enricher,
    is_session_ssot_hook_active,
)
from lca.harness.session.emit import emit
from lca.infrastructure.session.bindings import (
    active_publish_session,
    resolve_raw_session,
)
from lca_kernel.events.payloads.payloads import SpineEventPayload
from lca_kernel.events.session.session import SessionEvent, SessionProtocol

_log = structlog.get_logger(__name__)


def _fact_label(event: Any) -> str:
    """Best-effort identity of a catalog event for the drop log."""
    category = getattr(event, "category", None)
    return str(getattr(category, "value", None) or category or type(event).__name__)


def _require_publish_writer(session: object | None, *, fact: str, actor: str) -> object | None:
    """Resolve the publish writer; loud when a durable fact would be dropped.

    ``session`` 是调用方显式注入的 writer;缺省时经
    :func:`active_publish_session` 实时读取 active binding。绑定动作发生在
    run bind,晚于本模块 import,所以缺省读取必须走函数入口 —— 直接
    ``from ... import _ACTIVE_SESSION`` 会冻结 import 时的 ``None``。

    显式注入的若是 raw :class:`Session`(reader seam),而 bound publish seam 的
    正是同一个 run,则改走 publish seam:spine ledger 的落盘 sink 挂在
    :class:`RunEventSessionBridge` 的 observer 上,绕开 bridge 的 append 会让
    事实进日志但不进 ledger。

    未绑定只能发生在 run bind 之前(boot / 诊断路径);此时事实无法落
    Session,必须留下可见记录,静默丢弃会让整条 journal 事实链空转。
    """
    bound = active_publish_session()
    writer = session if session is not None else bound
    if writer is None:
        _log.warning(
            "fact_gateway.unbound_drop",
            fact=fact,
            actor=actor,
            detail="no Session bound at emit; durable fact not committed",
        )
        return None
    return _prefer_publish_seam(writer, bound)


def _prefer_publish_seam(writer: object, bound: object | None) -> object:
    """Swap a raw Session for the bound publish seam covering the same run.

    The spine ledger sink is a bridge observer, so it only fires on appends made
    through the publish seam. A writer that cannot take the typed payload
    (``append(payload, *, producer)``) but resolves to the same Session as the
    bound seam is therefore rerouted; a genuinely different Session is left
    alone so an explicit writer still owns its own facts.
    """
    if bound is None or writer is bound:
        return writer
    if _supports_payload_append(writer) or not _supports_payload_append(bound):
        return writer
    raw = resolve_raw_session(writer)
    if raw is not None and raw is resolve_raw_session(bound):
        return bound
    return writer


def _record_to_receipt(record: SessionEvent) -> AppendReceipt:
    return AppendReceipt(
        event_type=record.type,
        seq=record.seq,
        session_id=record.session_id,
        time=record.time,
    )


def enrich_ep_payload(
    ep: str,
    payload: Mapping[str, Any],
    *,
    channel: str = "fact",
) -> dict[str, Any]:
    """Merge caller payload with active spine enrich seam (public wrapper)."""
    return _enrich_publish_payload(ep, payload, channel=channel)


def _enrich_publish_payload(
    ep: str,
    payload: Mapping[str, Any],
    *,
    channel: str = "fact",
) -> dict[str, Any]:
    """Merge caller payload with active enrich seam when Session hook is off."""
    caller = dict(payload)
    if is_session_ssot_hook_active():
        return caller
    enricher = get_active_spine_enricher()
    if enricher is not None:
        return enricher(
            execution_point=ep,
            channel=channel,
            caller_payload=caller,
            span_ctx=None,
        ).merged
    producers = get_active_field_producers()
    if producers is None:
        return caller
    from lca.infrastructure.observability.spine.spine.enrich import enrich_spine_payload

    enrich_result = enrich_spine_payload(
        producers=producers,
        execution_point=ep,
        channel=channel,  # type: ignore[arg-type]
        caller_payload=caller,
        span_ctx=None,
    )
    return enrich_result.merged


def _supports_payload_append(writer: object) -> bool:
    """True when ``append(payload, *, producer=...)`` (bridge / bus facade)."""
    append = getattr(writer, "append", None)
    if not callable(append):
        return False
    try:
        sig = inspect.signature(append)
    except (TypeError, ValueError):
        return False
    return "producer" in sig.parameters


def _receipt_from_bus_ref(ref: Any, *, event_type: str) -> AppendReceipt:
    """Map synthetic :class:`EventRef` from bridge/facade append → :class:`AppendReceipt`."""
    event_id = getattr(ref, "event_id", "")
    ts = getattr(ref, "ts", 0.0)
    if not isinstance(event_id, str) or ":" not in event_id:
        raise ValueError(f"invalid EventRef.event_id: {event_id!r}")
    session_id, seq_s = event_id.rsplit(":", 1)
    return AppendReceipt(
        event_type=event_type,
        seq=int(seq_s),
        session_id=session_id,
        time=int(float(ts) * 1000),
    )


def _catalog_session_for(publish_writer: object) -> SessionProtocol:
    """Raw Session for catalog/surface; unwrap bridge/facade when bound."""
    raw = resolve_raw_session(publish_writer)
    if raw is not None:
        return raw
    return cast("SessionProtocol", publish_writer)


class DefaultFactGateway(FactGateway):
    """把 ``Session.append`` 收口为唯一事实生产门面。

    Publish seam (bridge/facade) 只用于 spine EP;catalog / surface 始终写 raw Session。
    """

    def __init__(self, publish_writer: object) -> None:
        self._publish_writer = publish_writer
        self._catalog_session = _catalog_session_for(publish_writer)

    def append_catalog(self, event: Any, *, actor: str) -> AppendReceipt:
        """提交 typed catalog 事件(镜像 ``harness.session.emit``)。"""
        record = emit(self._catalog_session, event, actor=actor)
        from lca.contracts.models.observability.journal.catalog import JOURNAL_EVENT_CLASSES
        from lca.infrastructure.observability.facade.facade.facade import current_bound

        bound = current_bound()
        if bound is not None and bound.journal is not None:
            journal_event = event
            if type(event).__name__ == "ToolInvokedCommitted":
                from lca.contracts.models.observability.journal.journal import ToolInvoked

                journal_event = ToolInvoked(
                    tool_name=getattr(event, "tool_name", ""),
                    invocation_id=getattr(event, "invocation_id", ""),
                    ok=getattr(event, "ok", True),
                    latency_ms=getattr(event, "latency_ms", 0),
                    attempt=getattr(event, "attempt", 1),
                    error=getattr(event, "error", ""),
                    files=getattr(event, "files", ()),
                    arguments=getattr(event, "arguments", {}),
                    arguments_ref=getattr(event, "arguments_ref", None),
                    output_ref=getattr(event, "output_ref", None),
                    output_text=getattr(event, "output_text", None),
                    output_truncated=getattr(event, "output_truncated", False),
                    projected_state=getattr(event, "projected_state", {}),
                )
            elif type(event).__name__ not in JOURNAL_EVENT_CLASSES:
                journal_event = None

            if journal_event is not None:
                bound.journal.write(journal_event)
        return _record_to_receipt(record)

    def publish_ep(self, ep: str, payload: Mapping[str, Any], *, actor: str) -> AppendReceipt:
        """提交 spine EP 事实(category 鉴权 + I17 enrich + FieldProducer merge)。"""
        merged = _enrich_publish_payload(ep, payload)
        spine = SpineEventPayload.model_validate(
            {"execution_point": ep, "channel": "fact", "payload": merged}
        )
        if _supports_payload_append(self._publish_writer):
            # RunEventSessionBridge / SessionBusFacade: keep typed payload on the
            # observer path so SpineFileSink can build_record (ADR-0186).
            producer = cast("Any", DefaultFactGateway)
            ref = cast("Any", self._publish_writer).append(spine, producer=producer)
            return _receipt_from_bus_ref(ref, event_type=spine.category.value)
        data = spine.model_dump(mode="json")
        data.pop("category", None)
        record = self._catalog_session.append(spine.category.value, data, actor=actor)
        return _record_to_receipt(record)

    def append_diagnostic(self, diag: Any) -> AppendReceipt | None:
        """诊断事实默认不落盘(no-op)。"""
        del diag
        return None


def append_catalog_bound(
    event: Any,
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """Resolve bound writer; append catalog event; drop (loudly) when unbound.

    ``state`` is retained for call-site symmetry (step metadata lives on
    state; session binding lives on the publish seam).
    """
    del state
    writer = _require_publish_writer(session, fact=_fact_label(event), actor=actor)
    if writer is None:
        return None
    return DefaultFactGateway(writer).append_catalog(event, actor=actor)


def publish_ep_bound(
    ep: str,
    payload: Mapping[str, Any],
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """Resolve bound writer; append spine EP event; drop (loudly) when unbound."""
    del state
    writer = _require_publish_writer(session, fact=ep, actor=actor)
    if writer is None:
        return None
    return DefaultFactGateway(writer).publish_ep(ep, payload, actor=actor)


__all__ = [
    "DefaultFactGateway",
    "append_catalog_bound",
    "enrich_ep_payload",
    "publish_ep_bound",
]
