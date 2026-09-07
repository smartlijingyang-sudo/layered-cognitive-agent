"""Register an LCA agent run with the gateway coordinator + running-op index.

PR-2 Task 12 follow-up: after ``RunPort.create_and_dispatch`` succeeds,
``create_run`` calls :func:`register_gateway_run` so:

1. ``LcaAgentRuntimeCoordinator.start`` publishes ``agent_runtime_init``
   (required by ``refresh_ws_token`` EXISTS check).
2. ``RunningOperationStore.insert`` records the topic → run mapping
   (required by ``GET /v1/topics/{topic_id}/running-op``).
3. A background task pumps ``LiveRunProjection`` events into Redis
   via ``coordinator.handle_stamped`` (the WS broadcaster).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from starlette.requests import Request

from lca.contracts.models.observability.journal.journal import StampedEvent


def topic_id_from_body(body: dict[str, Any]) -> str:
    """Extract topic id from POST /runs body (camelCase or snake_case)."""
    for key in ("topic_id", "topicId"):
        raw = body.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    options = body.get("options")
    if isinstance(options, dict):
        for key in ("topic_id", "topicId"):
            raw = options.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return ""


def _stamped_payload(stamped: StampedEvent) -> dict[str, Any]:
    event_body = dict(stamped.data) if stamped.data else {}
    if "type" not in event_body:
        event_body["type"] = stamped.event_type or type(stamped.event).__name__
    return {"event": event_body}


async def _pump_gateway_tail(session: Any, coordinator: Any) -> None:
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


def _schedule_tail_pump(session: Any, coordinator: Any) -> None:
    if getattr(session, "_gateway_pump_task", None) is not None:
        return
    session._gateway_pump_task = asyncio.create_task(
        _pump_gateway_tail(session, coordinator),
        name=f"gateway-pump:{session.run_id}",
    )


async def register_gateway_run(
    request: Request,
    *,
    run_id: str,
    topic_id: str,
    agent_id: str,
    body: dict[str, Any],
) -> None:
    """Start gateway metadata + broadcast for one newly-created run."""
    coordinator = getattr(request.app.state, "agent_runtime_coordinator", None)
    registry = getattr(request.app.state, "registry", None)
    if coordinator is None or registry is None:
        return
    get_session = getattr(registry, "get", None)
    if not callable(get_session):
        return
    session = get_session(run_id)
    if session is None:
        return

    scope = str(body.get("scope") or "main")
    options = body.get("options")
    if isinstance(options, dict) and options.get("scope"):
        scope = str(options["scope"])

    parent_raw = body.get("parent_message_id") or body.get("parentMessageId")
    assistant_message_id = parent_raw if isinstance(parent_raw, str) and parent_raw else None

    await coordinator.start(
        run_id,
        ctx={
            "agent_id": agent_id,
            "topic_id": topic_id,
            "scope": scope,
            "assistant_message_id": assistant_message_id,
        },
    )
    _schedule_tail_pump(session, coordinator)


__all__ = ("register_gateway_run", "topic_id_from_body")
