"""Gate plugin helpers — resolve profile loop policy (ADR-0197)."""

from __future__ import annotations

from lca.cognition.brain.guard.loop_policy import LoopGuardPolicyView, StaticLoopGuardPolicy
from lca.contracts.models.core.policy.loop_policy import DEFAULT_LOOP_POLICY, LoopPolicyThresholds
from lca.contracts.protocols.think.loop_guard import LoopGuardPolicy
from lca.harness.plugin_api import PluginContext


def resolve_loop_policy(ctx: PluginContext) -> LoopGuardPolicy:
    policy = ctx.require("loop_guard_policy")
    if isinstance(policy, StaticLoopGuardPolicy):
        return policy
    thresholds = getattr(policy, "thresholds", None)
    if isinstance(thresholds, LoopPolicyThresholds):
        return StaticLoopGuardPolicy(LoopGuardPolicyView(thresholds=thresholds))
    raise TypeError(
        f"loop_guard_policy must implement LoopGuardPolicy, got {type(policy).__name__}"
    )


def resolve_loop_thresholds(ctx: PluginContext) -> LoopPolicyThresholds:
    return resolve_loop_policy(ctx).thresholds


__all__ = ["DEFAULT_LOOP_POLICY", "resolve_loop_policy", "resolve_loop_thresholds"]
