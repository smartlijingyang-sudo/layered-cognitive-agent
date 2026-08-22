"""标准 perceive PhaseExecutor。"""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    StandardPhaseExecutor,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.perceive.standard",
    phase=SemanticPhase.PERCEIVE,
    module="lca.plugins.phase_executors.perceive",
)


@plugin(
    id="phase.perceive.standard",
    Config=StandardPhaseConfig,
    provides=("phase.perceive.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.perceive.standard", StandardPhaseExecutor(SemanticPhase.PERCEIVE))


def create_executor() -> StandardPhaseExecutor:
    return StandardPhaseExecutor(SemanticPhase.PERCEIVE)
