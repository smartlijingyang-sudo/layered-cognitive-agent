"""Register an LCA agent run with the gateway coordinator + running-op index.

PR-2 Task 12 follow-up: after ``RunPort.create_and_dispatch`` succeeds,
``create_run`` calls :func:`register_gateway_run` so:

1. ``LcaAgentRuntimeCoordinator.start`` publishes ``agent_runtime_init``
   (required by ``refresh_ws_token`` EXISTS check).
2. ``RunningOperationStore.insert`` records the topic → run mapping
   (required by ``GET /v1/topics/{topic_id}/running-op``).
3. A background task observes the run's Session log and publishes
   AgentStreamEvents into Redis via ``coordinator.handle_stamped``
   (the WS broadcaster).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

from lca.application.runtime.coordinator.session_gateway_pump import (
    schedule_gateway_session_pump,
)


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
    schedule_gateway_session_pump(
        session,
        coordinator,
        assistant_message_id=assistant_message_id,
    )


__all__ = ("register_gateway_run", "topic_id_from_body")
