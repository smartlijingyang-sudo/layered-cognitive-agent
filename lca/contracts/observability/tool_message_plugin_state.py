"""Tool message pluginState persistence for Agent Gateway (ADR-0200 §5.3.1)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolMessagePluginStateStore(Protocol):
    """Write ``message_plugins.state`` (front-end ``pluginState``) by tool_call_id."""

    async def write(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        state: dict[str, Any],
    ) -> None: ...


__all__ = ("ToolMessagePluginStateStore",)
