"""标准 think PhaseExecutor。"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.think.standard",
    phase=SemanticPhase.THINK,
    module="lca.plugins.phase_executors.think",
)


@dataclass(frozen=True, slots=True)
class StandardThinkExecutor:
    """Create a decision through the profile-selected Brain capability."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        brain = StandardPhaseCapabilities(context.capabilities).brain
        if brain is None:
            return fallback_phase_result(
                phase=SemanticPhase.THINK,
                result_kind="decision",
                input=input,
            )
        return PhaseResult(result_kind="decision", payload=await brain.think(context.state))


@plugin(
    id="phase.think.standard",
    Config=StandardPhaseConfig,
    provides=("phase.think.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.think.standard", StandardThinkExecutor())


def create_executor() -> StandardThinkExecutor:
    return StandardThinkExecutor()


__all__ = ["StandardThinkExecutor", "create_executor"]
