"""ParseDecisionPlugin — optional hook to relabel Decision.action_type.

Primary classify path is ``think.classify`` (DefaultDecisionClassifier +
lab mapping use_tool → call_tool). This plugin remains for graph-level
hooks that want to override labels after classify.

Behaviour (override via ``config``):
  tool_calls non-empty → enabled_tool_action (default "call_tool")
  else if text non-empty → enabled_respond_action (default "respond")
  else → enabled_refuse_action (default "refuse")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import GraphPlugin, HookContext, register_plugin


@register_plugin
@dataclass(frozen=True)
class ParseDecisionPlugin(GraphPlugin):
    """Reclassify Decision.action_type based on LLMResponse content."""

    name: str = "default_parse_decision"
    kind: str = "parse_decision"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def on_decision(self, ctx: HookContext) -> HookContext:
        artifact = ctx.payload.get("artifact")
        if artifact is None:
            return ctx
        content = getattr(artifact, "content", None)
        if not isinstance(content, dict):
            return ctx

        tool_calls = content.get("tool_calls") or []
        text = content.get("response_text") or content.get("text") or ""
        text = str(text) if text else ""

        if tool_calls:
            action_type = self.config.get("enabled_tool_action", "call_tool")
        elif text.strip():
            action_type = self.config.get("enabled_respond_action", "respond")
        else:
            action_type = self.config.get("enabled_refuse_action", "refuse")

        if content.get("action_type") == action_type:
            return ctx

        new_content = {**content, "action_type": action_type}
        # Build a new artifact (Pydantic frozen → cannot mutate in-place).
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


__all__ = ["ParseDecisionPlugin"]
