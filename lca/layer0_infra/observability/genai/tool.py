"""ToolGenAIMapper —— ToolInvoked / ToolStarted / ToolDenied → gen_ai.tool.* 属性。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


class ToolGenAIMapper:
    event_type = "ToolInvoked"
    runtime_kind = "tool"

    def map(self, stamped: StampedEvent) -> dict[str, str]:
        from lca.contracts.models.observability.journal import ToolInvoked

        event = stamped.event
        if not isinstance(event, ToolInvoked):
            return {}
        attrs: dict[str, str] = {
            "gen_ai.tool.name": event.tool_name,
            "gen_ai.tool.call.id": event.invocation_id,
            "gen_ai.tool.call.ok": str(event.ok).lower(),
        }
        if event.latency_ms:
            attrs["gen_ai.tool.call.latency_ms"] = str(event.latency_ms)
        if event.error:
            attrs["gen_ai.tool.call.error"] = event.error[:500]
        return attrs
