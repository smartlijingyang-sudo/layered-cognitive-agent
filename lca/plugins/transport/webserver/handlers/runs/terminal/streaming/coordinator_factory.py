"""Factory for the production ``LcaAgentRuntimeCoordinator`` instance."""

from __future__ import annotations

from typing import Any

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import LcaAgentRuntimeCoordinator
from lca.contracts.observability.running_operation import RunningOperationStore
from lca.contracts.observability.tool_message_plugin_state import ToolMessagePluginStateStore
from lca.infrastructure.observability.stream import (
    LcaStreamEventManager,
    get_agent_runtime_redis_client,
)
from lca.infrastructure.observability.tool_message_plugin_state_store import (
    resolve_tool_message_plugin_state_store,
)


def build_agent_runtime_coordinator(
    store: RunningOperationStore,
    *,
    plugin_state_store: ToolMessagePluginStateStore | None = None,
) -> LcaAgentRuntimeCoordinator:
    """Wire coordinator with running-op metadata + pluginState DB writer."""

    plugin_writer = plugin_state_store or resolve_tool_message_plugin_state_store()

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
        await plugin_writer.write(
            run_id=run_id,
            tool_call_id=tool_call_id,
            state=state,
        )

    return LcaAgentRuntimeCoordinator(
        stream_manager=LcaStreamEventManager(get_agent_runtime_redis_client()),
        translator=EventTranslator(),
        metadata_writer=metadata_writer,
        tool_state_writer=tool_state_writer,
    )


__all__ = ("build_agent_runtime_coordinator",)
