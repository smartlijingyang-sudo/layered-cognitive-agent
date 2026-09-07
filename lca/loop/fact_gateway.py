"""G0 单一事实生产门面(ADR-0194 §3.1)。

所有 durable 事实经本门面统一走 ``Session.append``;spine EP 在 hook 未激活时经本模块内聚的
enrich seam 合并 FieldProducer 字段(与 Session hook 同轨)。catalog / surface 事实委托
``harness.session.emit`` 或 raw ``Session.append``;spine EP 经 publish seam 保留 typed payload。
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, cast

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, FactGateway
from lca.contracts.protocols.loop.spine_publish import (
    get_active_field_producers,
    get_active_spine_enricher,
    is_session_ssot_hook_active,
)
from lca.harness.session.emit import emit
from lca.infrastructure.session._overflow_0.bindings import resolve_raw_session
from lca.plugins.events.publishers._session_publish import current_publish_session
from lca_kernel.events.payloads.payloads import SpineEventPayload
from lca_kernel.events.session.session import SessionEvent, SessionProtocol


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
        return _record_to_receipt(record)

    def append_surface(
        self,
        event_type: str,
        data: Mapping[str, Any],
        *,
        actor: str,
        surface_op: str = "append",
        visibility: str = "model",
    ) -> AppendReceipt:
        """提交 model-visible surface 节点(raw Session.append 形态)。"""
        record = self._catalog_session.append(
            event_type,
            dict(data),
            actor=actor,
            surface_op=surface_op,
            visibility=visibility,
        )
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


def _bound_publish_writer(
    *,
    session: object | None = None,
    state: AgentState | None = None,
) -> object | None:
    del state
    if session is not None:
        return session
    return current_publish_session()


def fact_gateway_for_emit(
    state: AgentState | None = None,
    *,
    session: object | None = None,
) -> DefaultFactGateway | None:
    """Resolve bound publish writer; ``None`` when unbound (tests / offline)."""
    writer = _bound_publish_writer(session=session, state=state)
    if writer is None:
        return None
    return DefaultFactGateway(writer)


def append_catalog_bound(
    event: Any,
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """``append_catalog`` with bound publish session; no-op if unbound."""
    writer = _bound_publish_writer(session=session, state=state)
    if writer is None:
        return None
    return DefaultFactGateway(writer).append_catalog(event, actor=actor)


def append_surface_bound(
    event_type: str,
    data: Mapping[str, Any],
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
    surface_op: str = "append",
    visibility: str = "model",
) -> AppendReceipt | None:
    """``append_surface`` with bound publish session; no-op if unbound."""
    writer = _bound_publish_writer(session=session, state=state)
    if writer is None:
        return None
    return DefaultFactGateway(writer).append_surface(
        event_type,
        data,
        actor=actor,
        surface_op=surface_op,
        visibility=visibility,
    )


def publish_ep_bound(
    ep: str,
    payload: Mapping[str, Any],
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """``publish_ep`` with bound publish session; no-op if unbound."""
    writer = _bound_publish_writer(session=session, state=state)
    if writer is None:
        return None
    return DefaultFactGateway(writer).publish_ep(ep, payload, actor=actor)


__all__ = [
    "DefaultFactGateway",
    "append_catalog_bound",
    "append_surface_bound",
    "enrich_ep_payload",
    "fact_gateway_for_emit",
    "publish_ep_bound",
]
