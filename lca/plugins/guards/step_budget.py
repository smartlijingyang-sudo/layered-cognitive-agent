"""Step budget guard plugin — Tier-3 (middleware)."""
from __future__ import annotations

from cordis import plugin
from pydantic import BaseModel


class BudgetExceededError(RuntimeError):
    """Raised when step or token budget is exhausted."""


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    max_steps: int = 100


def budget_check_middleware(
    phase: str,
    state,
    context,
    *,
    config: dict | None = None,
):
    """Check step budget before each step.

    Raises BudgetExceededError if state.step_count >= max_steps.
    """
    cfg = config or {}
    max_steps: int = cfg.get("max_steps", 100)
    step_count: int = getattr(state, "step_count", 0)
    if step_count >= max_steps:
        raise BudgetExceededError(f"Step budget exhausted: {step_count}/{max_steps}")
    return state


@plugin(name="lca-guard-step-budget")
async def setup(ctx, config: Config) -> None:
    def _listener(state):
        return budget_check_middleware(
            "agent.pre_step",
            state,
            None,
            config={"max_steps": config.max_steps},
        )

    ctx.events.on("agent.pre_step", _listener)
