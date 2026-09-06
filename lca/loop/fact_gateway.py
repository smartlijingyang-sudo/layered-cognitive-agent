"""G0 单一事实生产门面(ADR-0194 §3.1)。

所有 durable 事实经本门面统一走 ``Session.append``;P2-10..16 后续将 20 个
``spine_reflector_*`` publisher 迁移至此。catalog 事实委托
``harness.session.emit``;spine EP 在 hook 未激活时经 ``spine_enrich`` 合并
FieldProducer 字段(与 ``EmitPipeline`` / ``spine_hook`` 同轨)。

回滚开关(ADR-0194 §8,P1-09):``LCA_FACT_GATEWAY`` 未设或为真时走本模块;
显式 ``0``/``false``/``no``/``off`` 时 catalog 回退 ``harness.session.emit``,
spine EP 回退 ``publish_via_session``(delete-when:P5-01 Wave B 完成)。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Final

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, FactGateway
from lca.harness.session.emit import emit
from lca.infrastructure.observability.loop_cursor._spine_port import is_session_ssot_hook_active
from lca.infrastructure.session.bindings import resolve_session_for_emit
from lca.plugins.observability.spine.spine_enrich import get_active_spine_enricher
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.session import SessionEvent, SessionProtocol

_ENV_FACT_GATEWAY: Final[str] = "LCA_FACT_GATEWAY"
_FACT_GATEWAY_DISABLED = frozenset({"0", "false", "no", "off"})


def is_fact_gateway_enabled() -> bool:
    """Return False only when ``LCA_FACT_GATEWAY`` is explicitly disabled."""
    raw = os.environ.get(_ENV_FACT_GATEWAY)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _FACT_GATEWAY_DISABLED


def reset_fact_gateway_env(*, enabled: bool | None = None) -> None:
    """Test-only: set, clear, or default ``LCA_FACT_GATEWAY``."""
    if enabled is None:
        os.environ.pop(_ENV_FACT_GATEWAY, None)
    elif enabled:
        os.environ[_ENV_FACT_GATEWAY] = "1"
    else:
        os.environ[_ENV_FACT_GATEWAY] = "0"


def _record_to_receipt(record: SessionEvent) -> AppendReceipt:
    return AppendReceipt(
        event_type=record.type,
        seq=record.seq,
        session_id=record.session_id,
        time=record.time,
    )


def _resolve_spine_payload(
    ep: str,
    payload: Mapping[str, Any],
    *,
    channel: str = "fact",
) -> dict[str, Any]:
    """Merge caller payload with active spine enricher when hook is off."""
    caller = dict(payload)
    if is_session_ssot_hook_active():
        return caller
    enricher = get_active_spine_enricher()
    if enricher is None:
        return caller
    enrich_result = enricher(
        execution_point=ep,
        channel=channel,
        caller_payload=caller,
        span_ctx=None,
    )
    return enrich_result.merged


def _legacy_append_catalog(writer: object, event: Any, *, actor: str) -> AppendReceipt:
    """Catalog rollback: direct ``harness.session.emit`` (pre-P1-06 path)."""
    record = emit(writer, event, actor=actor)  # type: ignore[arg-type]
    return _record_to_receipt(record)


def _legacy_publish_ep(
    writer: object,
    ep: str,
    payload: Mapping[str, Any],
    *,
    actor: str,
) -> AppendReceipt:
    """Spine rollback: ``publish_via_session`` (pre-P1-02 reflector path)."""
    from lca.plugins.events.publishers._session_publish import (
        publish_via_session,
        reset_publish_session,
        set_publish_session,
    )
    from lca.plugins.events.publishers.spine_reflector_runtime.plugin import ReflectorClass

    spine = SpineEventPayload(execution_point=ep, channel="fact", payload=dict(payload))
    token = set_publish_session(writer)
    try:
        publish_via_session(spine, producer=ReflectorClass)
    finally:
        reset_publish_session(token)
    session = writer  # type: ignore[assignment]
    count = session.event_count  # type: ignore[attr-defined]
    record = session.event_at(count - 1)  # type: ignore[attr-defined]
    if record is None:
        raise RuntimeError(f"legacy publish_ep produced no session event for {ep!r}")
    return _record_to_receipt(record)


class DefaultFactGateway(FactGateway):
    """把 ``Session.append`` 收口为唯一事实生产门面。"""

    def __init__(self, session: SessionProtocol) -> None:
        self._session = session

    def append_catalog(self, event: Any, *, actor: str) -> AppendReceipt:
        """提交 typed catalog 事件(镜像 ``harness.session.emit``)。"""
        record = emit(self._session, event, actor=actor)
        return _record_to_receipt(record)

    def publish_ep(self, ep: str, payload: Mapping[str, Any], *, actor: str) -> AppendReceipt:
        """提交 spine EP 事实(镜像 ``publish_via_session`` + enrich seam)。"""
        merged = _resolve_spine_payload(ep, payload)
        spine = SpineEventPayload(execution_point=ep, channel="fact", payload=merged)
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
    if is_fact_gateway_enabled():
        return DefaultFactGateway(writer).append_catalog(event, actor=actor)  # type: ignore[arg-type]
    return _legacy_append_catalog(writer, event, actor=actor)


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
    if is_fact_gateway_enabled():
        return DefaultFactGateway(writer).publish_ep(ep, payload, actor=actor)  # type: ignore[arg-type]
    return _legacy_publish_ep(writer, ep, payload, actor=actor)


__all__ = [
    "DefaultFactGateway",
    "append_catalog_bound",
    "fact_gateway_for_emit",
    "is_fact_gateway_enabled",
    "publish_ep_bound",
    "reset_fact_gateway_env",
]
