"""Loop intervention middleware as plugin -- detects consecutive identical tool calls.

Spec reference: SDD Task-9 / harness-spine-spec S3.8.3.
"""
from __future__ import annotations

from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.harness.plugin import (
    PluginContext,
    PluginKind,
    PluginManifest,
)


manifest = PluginManifest(
    id="lca.policy.loop_intervention",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.POLICY,
    seam_key="agent.after_act",
    middleware=("agent.after_act",),
)


async def loop_intervention_middleware(
    phase: str,
    state: dict,
    context: object,
    *,
    config: dict | None = None,
) -> dict:
    """Check for consecutive identical tool calls.

    If the last N tool calls are identical, set loop_intervention flag.
    Returns a new dict (does not mutate the original state).
    """
    cfg = config or {}
    threshold = cfg.get("threshold", 3)
    recent = state.get("recent_tools", [])

    if len(recent) >= threshold:
        last_n = recent[-threshold:]
        if len(set(last_n)) == 1:
            state = dict(state)
            state["loop_intervention"] = True
            return state

    return state


def apply(ctx: PluginContext, config: dict) -> None:
    """Register loop intervention middleware on the ``agent.after_act`` extension point."""
    registry = ctx.require("middleware_registry")
    registry.register(
        MiddlewareRegistration(
            seam_key="agent.after_act",
            priority=20,
            plugin_id="lca.policy.loop_intervention",
        ),
        lambda phase, state, context: loop_intervention_middleware(
            phase, state, context, config=config,
        ),
    )
