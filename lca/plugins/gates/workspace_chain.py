"""Workspace agent gate chain — named factory ``gate.workspace-agent``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin

_CHAIN_KEYS: tuple[str, ...] = (
    "gate.repeat-tool-call",
    "gate.tool-loop-breaker",
    "gate.progress-loop-detector",
    "gate.terminal-respond",
    "gate.artifact-respond-injector",
)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def _build_workspace_agent_gate(ctx) -> object:
    from lca.layer1_cognitive.brain.decision_gates.chained import ChainedDecisionGate

    gates = []
    for key in _CHAIN_KEYS:
        factory = ctx.inject(key)
        if factory is None:
            continue
        gates.append(factory() if callable(factory) else factory)
    return ChainedDecisionGate(*gates)


@plugin(
    name="gate.workspace-agent",
    provides=["gate.workspace-agent"],
    requires=list(_CHAIN_KEYS),
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Compose the workspace agent gate chain from individual gate plugins.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide ``gate.workspace-agent`` assembled from individual gate plugins."""

    def factory() -> object:
        return _build_workspace_agent_gate(ctx)

    ctx.provide("gate.workspace-agent", factory)
