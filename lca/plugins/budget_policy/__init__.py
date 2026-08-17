"""Budget check middleware as plugin -- replaces hardcoded budget_check_hook.

Spec reference: SDD Task-8 / harness-spine-spec S3.8.4.
"""

from __future__ import annotations

from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.harness.plugin import (
    PluginContext,
    PluginKind,
    PluginManifest,
)


class BudgetExceededError(RuntimeError):
    """Raised when step or token budget is exhausted."""


manifest = PluginManifest(
    id="lca.policy.budget",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.POLICY,
    seam_key="agent.pre_step",
    middleware=("agent.before_step",),
)


async def budget_check_middleware(
    phase: str,
    state: object,
    context: object,
    *,
    config: dict | None = None,
) -> object:
    """Check step budget before each step.

    Raises ``BudgetExceededError`` if ``state.step_count >= max_steps``.
    Returns the state unchanged when under budget.
    """
    cfg = config or {}
    max_steps: int = cfg.get("max_steps", 100)
    step_count: int = getattr(state, "step_count", 0)

    if step_count >= max_steps:
        raise BudgetExceededError(f"Step budget exhausted: {step_count}/{max_steps}")
    return state


def apply(ctx: PluginContext, config: dict) -> None:
    """Register budget check middleware on the ``agent.before_step`` extension point."""
    registry = ctx.require("middleware_registry")
    registry.register(
        MiddlewareRegistration(
            seam_key="agent.before_step",
            priority=10,
            plugin_id="lca.policy.budget",
        ),
        lambda phase, state, context: budget_check_middleware(
            phase,
            state,
            context,
            config=config,
        ),
    )
