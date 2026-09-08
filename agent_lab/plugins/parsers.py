"""ParseDecisionPlugin — drives the LLMResponse → Decision.action_type tree.

Before this plugin existed, the heuristic lived inside
``agent_lab.adapters.lca_think._default_parser`` and branched on the
LLMResponse content (tool_calls / text / empty). The branch moved here
so the adapter is a thin dict⇄dataclass translator and the cognitive
policy lives in one plugin-able place.

Behaviour (override via ``config``):
  tool_calls (list of NativeToolCall-shaped dicts in artifact.content["tool_calls"]):
    non-empty  → action_type = "call_tool"
  else if text is non-empty:
    action_type = "respond"
  else:
    action_type = "refuse"

The plugin only mutates the artifact's ``action_type`` field and leaves
all other fields (``decision_id``, ``tool_calls``, ``rationale``,
``confidence``, ``response_text``) untouched. The adapter's
``_default_parser`` heuristic is still the fallback when no plugin is
configured (backward-compat for callers that import
``LcaThinkParseProvider`` directly).

Configuration:
  enabled_tool_action (str) — override default "call_tool" label
  enabled_respond_action (str) — override default "respond" label
  enabled_refuse_action (str) — override default "refuse" label
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
