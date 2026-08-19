"""Loop intervention guard plugin — Tier-3 (middleware)."""
from __future__ import annotations

from cordis import plugin
from pydantic import BaseModel


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    threshold: int = 3


def loop_intervention_middleware(
    phase: str,
    state: dict,
    context,
    *,
    config: dict | None = None,
) -> dict:
    """Check for consecutive identical tool calls."""
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


@plugin(name="lca-guard-loop-intervention")
async def setup(ctx, config: Config) -> None:
    def _listener(call_result, state):
        return loop_intervention_middleware(
            "agent.after_act",
            state,
            None,
            config={"threshold": config.threshold},
        )

    ctx.events.on("agent.after_act", _listener)
