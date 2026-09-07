"""Append model-visible tool result surface events (ADR-0201 / ADR-0193 write path)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.infrastructure.session.projections.tool_result_message import build_tool_surface_data
from lca.loop.fact_gateway import append_surface_bound
from lca_kernel.events.fold.fold import SURFACE_TOOL_RESULT_TYPE


def append_tool_result_surface(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    outcome: str,
    observation: Observation | None,
    latency_ms: int | None = None,
    session: object | None = None,
    actor: str = "body",
    enriched_fields: dict[str, Any] | None = None,
) -> AppendReceipt | None:
    """Append one ``body.tool.execute.end`` surface node with FC ``role=tool`` message."""
    if not invocation_id.strip():
        return None
    fields = dict(enriched_fields or {})
    ok = fields.get("ok") if "ok" in fields else None
    data = build_tool_surface_data(
        tool_name=str(fields.get("tool_name", tool_name)),
        invocation_id=str(fields.get("invocation_id", invocation_id)),
        attempt=int(fields.get("attempt", attempt)),
        outcome=str(fields.get("outcome", outcome)),
        observation=observation,
        latency_ms=latency_ms if latency_ms is not None else fields.get("latency_ms"),  # type: ignore[arg-type]
        ok=ok if isinstance(ok, bool) else None,
    )
    return append_surface_bound(
        SURFACE_TOOL_RESULT_TYPE,
        data,
        actor=actor,
        surface_op="append",
        session=session,
    )


__all__ = ["append_tool_result_surface"]
