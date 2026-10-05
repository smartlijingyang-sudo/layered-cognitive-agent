"""Register an LCA agent run with the gateway coordinator + running-op index.

Any dispatcher calls :func:`register_gateway_run` after
``RunPort.create_and_dispatch`` succeeds, so:

1. ``LcaAgentRuntimeCoordinator.start`` publishes ``agent_runtime_init``
   (required by ``refresh_ws_token`` EXISTS check).
2. ``RunningOperationStore.insert`` records the topic → run mapping
   (required by ``GET /v1/topics/{topic_id}/running-op``).
3. A background task observes the run's Session log and publishes
   AgentStreamEvents into Redis via ``coordinator.handle_stamped``
   (the WS broadcaster).

The registrar takes the ``app`` and typed binding facts, never a ``Request``
and never a raw HTTP body. In-process dispatchers (rooms, scheduled cron
handoff) hold an ``app`` and have no body to fabricate. The three
``*_from_body`` parsers keep HTTP-body shape knowledge on the HTTP side.
"""

from __future__ import annotations

from typing import Any

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


def scope_from_body(body: dict[str, Any]) -> str:
    """Extract the gateway scope from POST /runs body; ``options.scope`` wins."""
    options = body.get("options")
    if isinstance(options, dict) and options.get("scope"):
        return str(options["scope"])
    return str(body.get("scope") or "main")


def parent_message_id_from_body(body: dict[str, Any]) -> str | None:
    """Extract the assistant message this run continues, if the body names one."""
    raw = body.get("parent_message_id") or body.get("parentMessageId")
    return raw if isinstance(raw, str) and raw else None


async def register_gateway_run(
    app: Any,
    *,
    run_id: str,
    topic_id: str,
    agent_id: str,
    scope: str = "main",
    assistant_message_id: str | None = None,
    user_id: str = "",
    assistant_id: str = "",
) -> None:
    """Start gateway metadata + broadcast for one newly-created run."""
    coordinator = getattr(app.state, "agent_runtime_coordinator", None)
    registry = getattr(app.state, "registry", None)
    if coordinator is None or registry is None:
        return
    get_session = getattr(registry, "get", None)
    if not callable(get_session):
        return
    # registry.get 无类型(duck-type 会话);Any 显式声明避免 callable() 窄化为 object。
    session: Any = get_session(run_id)
    if session is None:
        return
    # 缺陷1修复：把 topic_id 落到 session，跨 run 会话自愈日志按 topic 归档。
    # 不覆盖已有值：run 请求带着 topic_id 进 create_run_session，绑定发生在
    # dispatch 之前，那次写入才是权威。这里只补没带 topic 的调用方。
    if topic_id and not getattr(session, "topic_id", ""):
        session.topic_id = topic_id

    resolved_user_id = user_id or getattr(session, "user_id", "") or None
    resolved_assistant_id = assistant_id or getattr(session, "assistant_id", "") or None

    if resolved_assistant_id and not getattr(session, "assistant_id", None):
        session.assistant_id = resolved_assistant_id
    if agent_id and not getattr(session, "agent_id", None):
        session.agent_id = agent_id

    await coordinator.start(
        run_id,
        ctx={
            "agent_id": agent_id,
            "topic_id": topic_id,
            "scope": scope,
            "assistant_message_id": assistant_message_id,
            "user_id": resolved_user_id,
            "assistant_id": resolved_assistant_id,
        },
    )
    schedule_gateway_session_pump(
        session,
        coordinator,
        assistant_message_id=assistant_message_id,
        assistant_id=resolved_assistant_id,
    )


__all__ = (
    "parent_message_id_from_body",
    "register_gateway_run",
    "scope_from_body",
    "topic_id_from_body",
)
