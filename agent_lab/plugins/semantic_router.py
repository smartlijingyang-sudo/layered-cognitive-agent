"""SemanticRouterPlugin — map artifact schema_ref → semantic hook events.

The runner only emits AFTER_NODE_EXECUTE with an outputs dict. This plugin
owns the business schema table (decision.v1 → on_decision, …) and fans
those events out to sibling plugins before outputs propagate on edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import (
    GraphPlugin,
    HookContext,
    HookEvent,
    fanout_hooks,
    register_plugin,
)

_DEFAULT_SCHEMA_HOOKS: dict[str, str] = {
    "decision.v1": "on_decision",
    "observation.v1": "on_observation",
    "reflection.v1": "on_reflection",
}


@register_plugin
@dataclass(frozen=True)
class SemanticRouterPlugin(GraphPlugin):
    """Route node outputs to semantic hooks by schema_ref (config-driven)."""

    name: str = "default_semantic_router"
    kind: str = "semantic_router"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def after_node_execute(self, ctx: HookContext) -> HookContext:
        outputs = ctx.payload.get("outputs")
        if not isinstance(outputs, dict) or not outputs:
            return ctx
        schema_hooks = self.config.get("schema_hooks") or _DEFAULT_SCHEMA_HOOKS
        plugins = ctx.payload.get("plugins") or []
        if not plugins:
            return ctx

        rewritten = dict(outputs)
        extra_payload: dict[str, Any] = {}
        for port_id, artifact in outputs.items():
            schema_ref = getattr(artifact, "schema_ref", "") or ""
            event_name = schema_hooks.get(schema_ref)
            if not event_name:
                continue
            try:
                event = HookEvent(event_name)
            except ValueError:
                continue
            sub = HookContext(
                event=event,
                spec_id=ctx.spec_id,
                subgraph_path=ctx.subgraph_path,
                node_id=ctx.node_id,
                node_factory=ctx.node_factory,
                artifact_digest=getattr(artifact, "short_id", lambda: "")(),
                payload={
                    "artifact": artifact,
                    "port_id": port_id,
                    "schema_ref": schema_ref,
                },
            )
            new_sub = fanout_hooks(list(plugins), event, sub)
            new_artifact = new_sub.payload.get("artifact", artifact)
            rewritten[port_id] = new_artifact if new_artifact is not None else artifact
            # Preserve non-artifact side channels (e.g. memory_candidates).
            for key, value in new_sub.payload.items():
                if key in {"artifact", "port_id", "schema_ref"}:
                    continue
                extra_payload[key] = value

        new_payload = {**ctx.payload, "outputs": rewritten, **extra_payload}
        return ctx.with_value(payload=new_payload)


__all__ = ["SemanticRouterPlugin"]
