"""Observe-wildcard control contribution plugin (ADR-0074 Phase 3b).

Provides the ``control.observe.wildcard`` capability as an independent plugin,
enabling per-slot substitution without replacing the entire control surface.
This is the explicit no-op owner for the cross-cutting ``observe.*`` control slot.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class ObserveWildcardExecutor:
    """Explicit no-op owner for the cross-cutting ``observe.*`` control slot."""

    async def execute(self, _context: PhaseContext, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(result_kind="control", payload={"verdict": "allow"})


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.observe.wildcard",
    Config=Config,
    provides=["control.observe.wildcard"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.STOP,
            role=ContributionRole.OBSERVE,
            executor="control.observe.wildcard",
            output="observe.*",
            order=2,
        )
    ],
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.observe.wildcard", ObserveWildcardExecutor())


__all__ = ["Config", "ObserveWildcardExecutor", "setup"]
