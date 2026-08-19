"""AgentService plugin — Tier-1 (to be merged into session_service in follow-up)."""
from __future__ import annotations

from cordis import plugin


class AgentService:
    """Convenience facade for recording agent-lifecycle events to a session store."""

    async def record_assistant_response(self, *args, **kwargs):
        raise NotImplementedError("use session_service.record(ASSISTANT_MESSAGE) instead")

    async def record_tool_call(self, *args, **kwargs):
        raise NotImplementedError("use session_service.record(TOOL_CALL) instead")

    async def record_tool_result(self, *args, **kwargs):
        raise NotImplementedError("use session_service.record(TOOL_RESULT) instead")

    async def record_turn_boundary(self, *args, **kwargs):
        raise NotImplementedError("use session_service.record(TURN_START/END) instead")

    async def record_step_boundary(self, *args, **kwargs):
        raise NotImplementedError("use session_service.record(STEP_START/END) instead")


@plugin(name="lca-agent-service")
async def setup(ctx, config) -> None:
    ctx.provide("agent_service", AgentService())
