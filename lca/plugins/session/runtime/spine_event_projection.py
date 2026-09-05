"""Project committed Session events into in-process :class:`EventRecord`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.infrastructure.observability.spine.event_record import Channel, EventRecord, Phase
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
from lca_kernel.events.payloads_spine import SPINE_EVENT_CATEGORIES, category_to_spine_ep
from lca_kernel.events.session import SessionEvent, SessionProtocol

__all__ = ["session_event_to_event_record"]


def _resolve_execution_point(event_type: str, data: dict[str, Any]) -> str | None:
    explicit = data.get("execution_point")
    if isinstance(explicit, str) and explicit in EXECUTION_POINTS:
        return explicit
    if event_type in EXECUTION_POINTS:
        return event_type
    if event_type in SPINE_EVENT_CATEGORIES:
        return category_to_spine_ep(event_type)
    if event_type.startswith("spine."):
        return category_to_spine_ep(event_type)
    return None


def session_event_to_event_record(
    session: SessionProtocol,
    event: SessionEvent,
) -> EventRecord | None:
    """Best-effort spine projection for Session-observer consumers (anomaly).

    Returns ``None`` when ``event.type`` is not spine-shaped — domain
    session events (``turn.started.v1`` etc.) are intentionally skipped.
    """
    data = dict(event.data)
    execution_point = _resolve_execution_point(event.type, data)
    if execution_point is None:
        return None

    channel_raw = data.get("channel", "fact")
    channel: Channel = channel_raw if channel_raw in ("fact", "control", "error", "diagnostic") else "fact"
    phase_raw = data.get("phase", "live")
    phase: Phase = phase_raw if phase_raw in ("live", "orphan") else "live"
    when = datetime.fromtimestamp(event.time / 1000.0, tz=UTC)

    span_id = data.get("span_id")
    if not isinstance(span_id, str) or not span_id:
        span_id = f"lca-seq-{event.seq:08x}"

    return EventRecord(
        execution_point=execution_point,
        channel=channel,
        span_id=span_id,
        parent_span_id=data.get("parent_span_id")
        if isinstance(data.get("parent_span_id"), str)
        else None,
        sequence=max(event.seq + 1, 1),
        epoch=max(int(data.get("epoch", 1)), 1),
        causality_id=f"session:{session.id}:{event.seq}",
        outcome=data.get("outcome"),
        when=when,
        when_corrected=when,
        prev_event_hash=data.get("prev_event_hash")
        if isinstance(data.get("prev_event_hash"), str)
        else None,
        run_id=session.id,
        step_id=data.get("step_id") if isinstance(data.get("step_id"), str) else None,
        payload=data,
        phase=phase,
        reason=data.get("reason") if isinstance(data.get("reason"), str) else None,
        trace_id=data.get("trace_id") if isinstance(data.get("trace_id"), str) else None,
    )
