"""G0 单一事实生产门面(ADR-0194 §3.1)。

所有 durable 事实经本门面统一走 ``Session.append``;spine EP 在 hook 未激活时经本模块内聚的
enrich seam 合并 FieldProducer 字段(与 Session hook 同轨)。catalog 事实委托
``harness.session.emit``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, FactGateway
from lca.contracts.protocols.loop.spine_publish import (
    get_active_field_producers,
    get_active_spine_enricher,
    is_session_ssot_hook_active,
)
from lca.harness.session.emit import emit
from lca.infrastructure.session._overflow_0.bindings import resolve_session_for_emit
from lca_kernel.events.payloads.payloads import SpineEventPayload
from lca_kernel.events.session.session import SessionEvent, SessionProtocol


def _record_to_receipt(record: SessionEvent) -> AppendReceipt:
    return AppendReceipt(
        event_type=record.type,
        seq=record.seq,
        session_id=record.session_id,
        time=record.time,
    )


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


class DefaultFactGateway(FactGateway):
    """把 ``Session.append`` 收口为唯一事实生产门面。"""

    def __init__(self, session: SessionProtocol) -> None:
        self._session = session

    def append_catalog(self, event: Any, *, actor: str) -> AppendReceipt:
        """提交 typed catalog 事件(镜像 ``harness.session.emit``)。"""
        record = emit(self._session, event, actor=actor)
        return _record_to_receipt(record)

    def publish_ep(self, ep: str, payload: Mapping[str, Any], *, actor: str) -> AppendReceipt:
        """提交 spine EP 事实(category 鉴权 + I17 enrich + FieldProducer merge)。"""
        merged = _enrich_publish_payload(ep, payload)
        spine = SpineEventPayload.model_validate(
            {"execution_point": ep, "channel": "fact", "payload": merged}
        )
        data = spine.model_dump(mode="json")
        data.pop("category", None)
        record = self._session.append(spine.category.value, data, actor=actor)
        return _record_to_receipt(record)

    def append_diagnostic(self, diag: Any) -> AppendReceipt | None:
        """诊断事实默认不落盘(no-op)。"""
        del diag
        return None


def fact_gateway_for_emit(
    state: AgentState | None = None,
    *,
    session: object | None = None,
) -> DefaultFactGateway | None:
    """Resolve bound Session writer; ``None`` when unbound (tests / offline)."""
    writer = session if session is not None else resolve_session_for_emit(state)
    if writer is None:
        return None
    return DefaultFactGateway(writer)  # type: ignore[arg-type]


def append_catalog_bound(
    event: Any,
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """``append_catalog`` with ``resolve_session_for_emit``; no-op if unbound."""
    writer = session if session is not None else resolve_session_for_emit(state)
    if writer is None:
        return None
    return DefaultFactGateway(writer).append_catalog(event, actor=actor)  # type: ignore[arg-type]


def publish_ep_bound(
    ep: str,
    payload: Mapping[str, Any],
    *,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str,
) -> AppendReceipt | None:
    """``publish_ep`` with ``resolve_session_for_emit``; no-op if unbound."""
    writer = session if session is not None else resolve_session_for_emit(state)
    if writer is None:
        return None
    return DefaultFactGateway(writer).publish_ep(ep, payload, actor=actor)  # type: ignore[arg-type]


__all__ = [
    "DefaultFactGateway",
    "append_catalog_bound",
    "fact_gateway_for_emit",
    "publish_ep_bound",
]
