"""ToolDispatchGuardPlugin — short-circuit empty / None tool names.

Before this plugin existed, ``nodes/tool/dispatch_tool/plugin.py``
contained::

    if tool in (None, "__none__"):
        return {...} # 返回空 receipt

That branch moves here. The plugin runs on the on_decision hook
(because the dispatch node's input is a ToolIntent-shaped artifact
whose content.action_type == "call_tool" and content.tool_calls[*].
name carries the requested tool name).

When the plugin sees ``name in (None, "", "__none__")`` it rewrites the
artifact's ``denied: True`` flag so the dispatch node returns a denial
receipt instead of attempting to resolve an empty tool.

Backward-compat: when no ToolDispatchGuardPlugin is configured, the
dispatch node still does its own short-circuit. Production graphs that
want the plugin-driven path register this plugin and remove the
short-circuit from the node (see agent_loop.yaml's plugins block).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import GraphPlugin, HookContext, register_plugin

_NONE_TOOL_NAMES = {None, "", "__none__"}


@register_plugin
@dataclass(frozen=True)
class ToolDispatchGuardPlugin(GraphPlugin):
    """Reject tool dispatches with empty / placeholder tool names."""

    name: str = "default_tool_dispatch_guard"
    kind: str = "tool_dispatch_guard"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def on_decision(self, ctx: HookContext) -> HookContext:
        artifact = ctx.payload.get("artifact")
        if artifact is None:
            return ctx
        content = getattr(artifact, "content", None)
        if not isinstance(content, dict):
            return ctx
        if content.get("action_type") != "call_tool":
            return ctx
        tool_calls = content.get("tool_calls") or []
        if not tool_calls:
            return ctx
        # Inspect every tool call's name. If any is None/empty, mark
        # the artifact as denied; downstream nodes treat ``denied: True``
        # as a fast-path skip.
        denied = any(
            tc.get("name") in _NONE_TOOL_NAMES if isinstance(tc, dict) else True
            for tc in tool_calls
        )
        if not denied:
            return ctx
        new_content = {**content, "denied": True, "deny_reason": "no_tool_name"}
        try:
            from agent_lab.primitives.artifact import Artifact

            new_artifact = Artifact(
                kind=artifact.kind,
                content=new_content,
                schema_ref=getattr(artifact, "schema_ref", "decision.v1"),
            )
        except Exception:
            return ctx
        return ctx.with_value(payload={**ctx.payload, "artifact": new_artifact})


__all__ = ["ToolDispatchGuardPlugin"]
