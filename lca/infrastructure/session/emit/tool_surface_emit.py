"""Append model-visible tool result surface events (ADR-0201 / ADR-0193 write path)."""

from __future__ import annotations

from typing import Any, Protocol

from lca.contracts.models.core.execution.decision import Observation
from lca.infrastructure.session.projections.tool_result_message import build_tool_surface_data
from lca_kernel.events.fold.fold import SURFACE_TOOL_RESULT_TYPE


class _SurfaceSession(Protocol):
    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        actor: str | None = None,
        surface_op: Any | None = None,
    ) -> object: ...


def _resolve_runtime_session(session: object | None) -> _SurfaceSession | None:
    if session is not None:
        if hasattr(session, "session"):
            inner = getattr(session, "session", None)
            if inner is not None:
                return inner  # type: ignore[return-value]
        return session  # type: ignore[return-value]
    from lca.infrastructure.session._overflow_0.bindings import resolve_session_for_emit
    from lca.plugins.events.publishers._session_publish import current_publish_session

    writer = current_publish_session() or resolve_session_for_emit()
    if writer is None:
        return None
    if hasattr(writer, "session"):
        return writer.session  # type: ignore[return-value]
    return writer  # type: ignore[return-value]


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
) -> object | None:
    """Append one ``body.tool.execute.end`` surface node with FC ``role=tool`` message."""
    if not invocation_id.strip():
        return None
    target = _resolve_runtime_session(session)
    if target is None:
        return None
    fields = dict(enriched_fields or {})
    data = build_tool_surface_data(
        tool_name=str(fields.get("tool_name", tool_name)),
        invocation_id=str(fields.get("invocation_id", invocation_id)),
        attempt=int(fields.get("attempt", attempt)),
        outcome=str(fields.get("outcome", outcome)),
        observation=observation,
        latency_ms=latency_ms if latency_ms is not None else fields.get("latency_ms"),  # type: ignore[arg-type]
    )
    return target.append(
        SURFACE_TOOL_RESULT_TYPE,
        data,
        actor=actor,
        surface_op="append",
    )


__all__ = ["append_tool_result_surface"]
