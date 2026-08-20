"""Workspace agent gate chain — named factory ``gate.workspace-agent``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.chained import ChainedDecisionGate

_CHAIN_KEYS: tuple[str, ...] = (
    "gate.repeat-tool-call",
    "gate.tool-loop-breaker",
    "gate.progress-loop-detector",
    "gate.terminal-respond",
    "gate.artifact-respond-injector",
)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def _build_workspace_agent_gate(ctx: Context) -> ChainedDecisionGate:
    gates = []
    for key in _CHAIN_KEYS:
        factory = ctx.inject(key)
        if factory is None:
            continue
        gates.append(factory() if callable(factory) else factory)
    return ChainedDecisionGate(*gates)


@plugin(name="gate.workspace-agent")
async def setup(ctx: Context, config: Config) -> None:
    """Provide ``gate.workspace-agent`` assembled from individual gate plugins."""

    def factory() -> ChainedDecisionGate:
        return _build_workspace_agent_gate(ctx)

    ctx.provide("gate.workspace-agent", factory)
