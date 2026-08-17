"""AgentService plugin — agent lifecycle event recording.

Bridges the agent lifecycle with the session event log by providing a typed
facade over ``SessionStore.append()``.  Each recording method constructs the
correct event dataclass and forwards it to the store.

Spec reference: §2.2.3 event vocabulary in ``docs/specs/harness-spine-spec.md``.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.events import (
    AssistantResponded,
    StepEnded,
    StepStarted,
    ToolCalled,
    ToolCompleted,
    TurnEnded,
    TurnStarted,
)
from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.agent.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("agent_service",),
)

name = "lca.agent.service"


class AgentService:
    """Convenience facade for recording agent-lifecycle events to a session store.

    Every method delegates to ``store.append(event, actor=...)`` with the
    correct event type and field names.
    """

    async def record_assistant_response(
        self,
        store: Any,
        turn: int,
        step: int,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record an ``AssistantResponded`` event."""
        event = AssistantResponded(
            turn=turn,
            step=step,
            content=content,
            tool_calls=tool_calls,
        )
        await store.append(event, actor="agent_service")

    async def record_tool_call(
        self,
        store: Any,
        turn: int,
        step: int,
        call_id: str,
        tool_name: str,
        arguments_ref: str,
    ) -> None:
        """Record a ``ToolCalled`` event."""
        event = ToolCalled(
            call_id=call_id,
            tool_name=tool_name,
            arguments_ref=arguments_ref,
        )
        await store.append(event, actor="agent_service")

    async def record_tool_result(
        self,
        store: Any,
        turn: int,
        step: int,
        call_id: str,
        success: bool,
        result_ref: str,
        error: str | None = None,
    ) -> None:
        """Record a ``ToolCompleted`` event."""
        event = ToolCompleted(
            call_id=call_id,
            success=success,
            result_ref=result_ref,
            error=error,
        )
        await store.append(event, actor="agent_service")

    async def record_turn_boundary(
        self,
        store: Any,
        turn: int,
        event_type: str,
    ) -> None:
        """Record a ``TurnStarted`` or ``TurnEnded`` event.

        ``event_type`` must be ``"start"`` or ``"end"``.
        """
        if event_type == "start":
            event: TurnStarted | TurnEnded = TurnStarted(turn=turn)
        elif event_type == "end":
            event = TurnEnded(turn=turn, reason="completed")
        else:
            msg = f"Unknown turn event_type: {event_type!r}"
            raise ValueError(msg)
        await store.append(event, actor="agent_service")

    async def record_step_boundary(
        self,
        store: Any,
        turn: int,
        step: int,
        event_type: str,
    ) -> None:
        """Record a ``StepStarted`` or ``StepEnded`` event.

        ``event_type`` must be ``"start"`` or ``"end"``.
        """
        if event_type == "start":
            event: StepStarted | StepEnded = StepStarted(turn=turn, step=step)
        elif event_type == "end":
            event = StepEnded(turn=turn, step=step)
        else:
            msg = f"Unknown step event_type: {event_type!r}"
            raise ValueError(msg)
        await store.append(event, actor="agent_service")


def apply(ctx: Any, config: Any) -> None:
    """Register the ``AgentService`` at the ``agent_service`` seam."""
    service = AgentService()
    ctx.mount("agent_service", service)
