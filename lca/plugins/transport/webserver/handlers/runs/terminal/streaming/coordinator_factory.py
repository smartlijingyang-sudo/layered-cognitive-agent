"""Factory for the production ``LcaAgentRuntimeCoordinator`` instance."""

from __future__ import annotations

from typing import Any

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import LcaAgentRuntimeCoordinator
from lca.contracts.observability.running_operation import RunningOperationStore
from lca.infrastructure.observability.stream import (
    LcaStreamEventManager,
    get_agent_runtime_redis_client,
)


def build_agent_runtime_coordinator(
    store: RunningOperationStore,
) -> LcaAgentRuntimeCoordinator:
    """Wire coordinator with running-op metadata + noop tool_state writer."""

    async def metadata_writer(run_id: str, ctx: dict[str, Any]) -> None:
        await store.insert(
            run_id=run_id,
            topic_id=str(ctx.get("topic_id") or ""),
            agent_id=str(ctx.get("agent_id") or ""),
            assistant_message_id=ctx.get("assistant_message_id"),
            scope=str(ctx.get("scope") or "main"),
        )

    async def tool_state_writer(
        *,
        run_id: str,
        tool_call_id: str,
        state: dict[str, Any],
    ) -> None:
        del run_id, tool_call_id, state  # PR-4: pluginState DB write

    return LcaAgentRuntimeCoordinator(
        stream_manager=LcaStreamEventManager(get_agent_runtime_redis_client()),
        translator=EventTranslator(),
        metadata_writer=metadata_writer,
        tool_state_writer=tool_state_writer,
    )


__all__ = ("build_agent_runtime_coordinator",)
