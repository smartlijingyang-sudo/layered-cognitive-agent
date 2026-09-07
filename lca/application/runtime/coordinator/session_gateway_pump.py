"""Pump Session SSOT events into the agent-gateway Redis stream.

Production runs emit facts through ``Session.append`` (spine EPs like
``llm.stream.token``, ``step.tool_call.record``, …). The legacy
``LiveRunProjection`` ring buffer is no longer fed on the hot path, so
gateway WS clients would only see ``agent_runtime_init`` /
``agent_runtime_end`` unless we observe the in-process Session log.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from lca.application.runtime.coordinator.session_catalog_map import (
    catalog_session_event_to_stamped,
    is_suppressed_spine_ep,
)
from lca.contracts.models.observability.journal.journal import StampedEvent
from lca.contracts.observability.registry.status import RunLifecycleStatus

_TERMINAL = frozenset(
    {
        RunLifecycleStatus.COMPLETED.value,
        RunLifecycleStatus.FAILED.value,
        RunLifecycleStatus.CANCELED.value,
        "completed",
        "failed",
        "canceled",
        "cancelled",
    }
)


def _stamped_payload(stamped: StampedEvent) -> dict[str, Any]:
    event_body = dict(stamped.data) if stamped.data else {}
    if "type" not in event_body:
        event_body["type"] = stamped.event_type or type(stamped.event).__name__
    return {"event": event_body}


def session_event_to_stamped(
    event_type: str,
    data: dict[str, Any],
    *,
    assistant_message_id: str | None = None,
) -> dict[str, Any] | None:
    """Map one committed Session event to an EventTranslator input envelope."""
    catalog = catalog_session_event_to_stamped(
        event_type,
        data,
        assistant_message_id=assistant_message_id,
    )
    if catalog is not None:
        return catalog

    parent = assistant_message_id or None

    if event_type == "thinking.delta.v1":
        # Session SSOT already publishes ``llm.stream.token`` for the same
        # delta via LlmSpineEmitter; translating both doubles every chunk.
        return None

    if event_type == "assistant.responded.v1":
        # ModelVisibleHook already commits ``spine.llm.request.header.assistant``
        # with the same assistant body; translating both duplicates reply text.
        return None

    execution_point = data.get("execution_point")
    if not execution_point and event_type.startswith("spine."):
        from lca_kernel.events.payloads.spine import category_to_spine_ep

        execution_point = category_to_spine_ep(event_type)

    payload_raw = data.get("payload")
    inner_payload = payload_raw if isinstance(payload_raw, dict) else {}
    category = (
        inner_payload.get("category")
        or data.get("category")
        or (event_type if event_type.startswith("spine.") else None)
    )
    if category == "spine.llm.request.header.assistant":
        execution_point = "llm.request.header.assistant"

    if execution_point and is_suppressed_spine_ep(execution_point):
        return None

    if execution_point:
        body: dict[str, Any] = {**data, **inner_payload}
        body["type"] = execution_point
        body["execution_point"] = execution_point
        if parent:
            body["parentMessageId"] = parent
        return {"event": body}

    return None


async def _publish_session_event(
    coordinator: Any,
    run_id: str,
    event_type: str,
    data: dict[str, Any],
    *,
    assistant_message_id: str | None,
) -> None:
    stamped = session_event_to_stamped(
        event_type,
        data,
        assistant_message_id=assistant_message_id,
    )
    if stamped is not None:
        await coordinator.handle_stamped(run_id, stamped)


def _run_is_terminal(session: Any) -> bool:
    status = getattr(session, "status", None)
    if status is not None and str(getattr(status, "value", status)) in _TERMINAL:
        return True
    return bool(getattr(session, "_closed", False))


async def _pump_gateway_session(
    session: Any,
    coordinator: Any,
    *,
    assistant_message_id: str | None,
) -> None:
    """Observe Session.append and publish AgentStreamEvents for one run."""
    run_id = session.run_id
    bound = getattr(session, "event_session", None)
    inner = getattr(getattr(bound, "bridge", None), "inner", None) if bound is not None else None

    if inner is None:
        await _pump_gateway_tail_fallback(session, coordinator)
        return

    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=512)
    published_seqs: set[int] = set()

    async def _publish_log_event(event: Any) -> None:
        seq = getattr(event, "seq", None)
        if isinstance(seq, int):
            if seq in published_seqs:
                return
            published_seqs.add(seq)
        await _publish_session_event(
            coordinator,
            run_id,
            event.type,
            dict(event.data),
            assistant_message_id=assistant_message_id,
        )

    def _observer(_sess: Any, event: Any) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    cancel = inner.observe(_observer)

    for prior in list(getattr(inner, "_log", ())):
        await _publish_log_event(prior)

    async def _drain_queue() -> None:
        while True:
            try:
                event = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            await _publish_log_event(event)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                await _drain_queue()
                if _run_is_terminal(session):
                    break
                continue
            await _publish_log_event(event)
    except asyncio.CancelledError:
        raise
    except Exception:
        return
    finally:
        await _drain_queue()
        with contextlib.suppress(Exception):
            cancel()
        with contextlib.suppress(Exception):
            await coordinator.synthesize_terminal_if_pending(run_id, session=session)


async def _pump_gateway_tail_fallback(session: Any, coordinator: Any) -> None:
    """Legacy LiveTail path when Session is not bound (tests / harness)."""
    run_id = session.run_id
    try:
        sub = session.tail.subscribe(after_seq=0)
        async for item in sub:
            if isinstance(item, StampedEvent):
                await coordinator.handle_stamped(run_id, _stamped_payload(item))
    except asyncio.CancelledError:
        raise
    except Exception:
        return
    finally:
        with contextlib.suppress(Exception):
            await coordinator.synthesize_terminal_if_pending(run_id, session=session)


def schedule_gateway_session_pump(
    session: Any,
    coordinator: Any,
    *,
    assistant_message_id: str | None,
) -> None:
    if getattr(session, "_gateway_pump_task", None) is not None:
        return
    session._gateway_pump_task = asyncio.create_task(
        _pump_gateway_session(
            session,
            coordinator,
            assistant_message_id=assistant_message_id,
        ),
        name=f"gateway-pump:{session.run_id}",
    )


__all__ = (
    "schedule_gateway_session_pump",
    "session_event_to_stamped",
)
