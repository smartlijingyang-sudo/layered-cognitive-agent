"""LcaAgentRuntimeCoordinator — LiveRunProjection fold → Redis stream.

Mirror of `apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts`.
Subscribes to `LiveRunProjection.tail` for one run, translates each
StampedEvent via EventTranslator, persists tool_state to DB
(spec §5.3.1) BEFORE publishing `tool_end`, and runs a watchdog to
synthesise a terminal event if the natural SpineClose is missing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.terminal_hints import (
    resolve_live_terminal_hint,
)
from lca.infrastructure.observability.stream import LcaStreamEventManager

MetadataWriter = Callable[[str, dict], Awaitable[None]]
ToolStateWriter = Callable[[str, str, dict], Awaitable[None]]


class LcaAgentRuntimeCoordinator:
    def __init__(
        self,
        *,
        stream_manager: LcaStreamEventManager,
        translator: EventTranslator,
        metadata_writer: MetadataWriter,
        tool_state_writer: ToolStateWriter,
    ) -> None:
        self._mgr = stream_manager
        self._translator = translator
        self._metadata_writer = metadata_writer
        self._tool_state_writer = tool_state_writer
        # Track which runs have already had their natural agent_runtime_end
        # published, so the watchdog does not double-publish.
        self._natural_terminal_published: set[str] = set()

    # ── Public surface ────────────────────────────────────────────────

    async def start(self, run_id: str, *, ctx: dict) -> None:
        """Register metadata and publish `agent_runtime_init`.

        Order: metadata_writer(run_id, ctx) THEN publish init.
        The init event is what useGatewayReconnect's EXISTS checks against.
        """
        await self._metadata_writer(run_id, ctx)
        await self._mgr.publish(
            run_id,
            "agent_runtime_init",
            {
                "agentId": ctx.get("agent_id"),
                "topicId": ctx.get("topic_id"),
                "userId": ctx.get("user_id"),
                "operationId": run_id,
                "uiMessages": ctx.get("ui_messages"),
            },
            step_index=0,
        )

    async def handle_stamped(self, run_id: str, stamped: dict) -> None:
        """Fold one StampedEvent to AgentStreamEvent and publish.

        spec §5.3.1: persist ``projected_state`` into ``messages[].pluginState``
        BEFORE publishing ``tool_end`` so the front-end refetch reads a
        populated row.
        """
        event = (stamped or {}).get("event") or {}
        etype = event.get("type")
        step_index = int(event.get("step_index") or event.get("stepIndex") or 0)

        await self._persist_tool_plugin_state(run_id, event, etype=etype)

        envelope = self._translator.translate(stamped)
        if envelope is None:
            return
        await self._mgr.publish(run_id, envelope["type"], envelope["data"], step_index=step_index)

        # Track natural terminal publication
        if envelope["type"] == "agent_runtime_end":
            self._natural_terminal_published.add(run_id)

    async def _persist_tool_plugin_state(
        self,
        run_id: str,
        event: dict,
        *,
        etype: str | None,
    ) -> None:
        if etype == "ToolStarted":
            payload = event.get("payload") or event.get("toolCalling") or {}
            if not isinstance(payload, dict):
                return
            tool_call_id = payload.get("id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                return
            arguments = payload.get("arguments")
            initial_state: dict[str, Any] = {
                "identifier": payload.get("identifier"),
                "apiName": payload.get("apiName"),
            }
            if isinstance(arguments, dict):
                initial_state.update(arguments)
            await self._tool_state_writer(
                run_id=run_id,
                tool_call_id=tool_call_id,
                state=initial_state,
            )
            return

        if etype != "ToolInvoked":
            return

        projected = event.get("projected_state")
        if not isinstance(projected, dict) or not projected:
            return
        payload = event.get("payload") or {}
        tool_call_id = (
            (payload.get("toolCalling") or {}).get("id") if isinstance(payload, dict) else None
        )
        if not isinstance(tool_call_id, str) or not tool_call_id:
            return
        await self._tool_state_writer(
            run_id=run_id,
            tool_call_id=tool_call_id,
            state=projected,
        )

    async def terminal(
        self,
        run_id: str,
        *,
        status: str,
        final_state: dict,
    ) -> None:
        """Publish a `agent_runtime_end` event with the given terminal state.

        Called from the natural SpineClose path. Idempotent: subsequent
        calls for the same run_id publish duplicates (the watchdog's
        job is to skip if `_natural_terminal_published` is set).
        """
        await self._mgr.publish(
            run_id,
            "agent_runtime_end",
            {
                "finalState": final_state,
                "reason": status,
                "reasonDetail": "",
                "phase": "execution_complete",
            },
            step_index=0,
        )
        self._natural_terminal_published.add(run_id)

    async def synthesize_terminal_if_pending(self, run_id: str, *, session) -> None:
        """Watchdog: if no natural agent_runtime_end was published but the
        session has reached a terminal status, synthesise one.

        spec §1 broken path #3: parent run with no live SpineClose must
        not hang the stream.
        """
        if run_id in self._natural_terminal_published:
            return
        hint = resolve_live_terminal_hint(session)
        # Only synthesise when the wire-side hint is actually terminal.
        if hint not in {"completed", "error", "interrupted"}:
            return
        final_state = getattr(session, "final_state", None) or {"status": hint}
        await self.terminal(run_id, status=hint, final_state=final_state)


__all__ = ("LcaAgentRuntimeCoordinator", "MetadataWriter", "ToolStateWriter")
