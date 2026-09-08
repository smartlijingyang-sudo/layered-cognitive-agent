"""ObservationRenderPlugin — render a tool receipt into model-visible text.

Before this plugin existed, ``nodes/tool/integrate_observation/plugin.py``
held a 2-branch success/error template inside its ``execute()``. The
template moved here; the node is now a thin passthrough that emits a
FACT carrying the raw receipt, and the plugin writes the rendered
``observation`` text artifact alongside (or replaces the receipt's
content for callers that want a single-artifact view).

Behaviour:
  status == "ok":
    text = f"[tool:{tool}] {result}"
  else:
    text = f"[tool-error] {error or status}"

The plugin rewrites the artifact content (or returns the existing
artifact unchanged if it has no status field).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import GraphPlugin, HookContext, register_plugin


@register_plugin
@dataclass(frozen=True)
class ObservationRenderPlugin(GraphPlugin):
    """Render a tool receipt's success/error into the observation artifact."""

    name: str = "default_observation_render"
    kind: str = "observation_render"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def on_observation(self, ctx: HookContext) -> HookContext:
        artifact = ctx.payload.get("artifact")
        if artifact is None:
            return ctx
        content = getattr(artifact, "content", None)
        if not isinstance(content, dict):
            return ctx
        if "status" not in content:
            return ctx

        status = content.get("status")
        tool = content.get("tool", "")
        if status == "ok":
            result = content.get("result", "")
            text = f"[tool:{tool}] {result}"
        elif status == "no_effect":
            action = content.get("action_type") or "respond"
            snippet = content.get("response_text") or ""
            text = f"[no-effect:{action}] {snippet}".rstrip()
        else:
            text = f"[tool-error] {content.get('error') or status}"
        if content.get("text") == text:
            return ctx

        new_content = {**content, "text": text}
        try:
            from agent_lab.primitives.artifact import Artifact

            new_artifact = Artifact(
                kind=artifact.kind,
                content=new_content,
                schema_ref=getattr(artifact, "schema_ref", "observation.v1"),
            )
        except Exception:
            return ctx
        return ctx.with_value(payload={**ctx.payload, "artifact": new_artifact})


__all__ = ["ObservationRenderPlugin"]
