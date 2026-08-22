"""标准 reflect PhaseExecutor。"""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    StandardPhaseExecutor,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.reflect.standard",
    phase=SemanticPhase.REFLECT,
    module="lca.plugins.phase_executors.reflect",
)


@plugin(
    id="phase.reflect.standard",
    Config=StandardPhaseConfig,
    provides=("phase.reflect.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.reflect.standard", StandardPhaseExecutor(SemanticPhase.REFLECT))


def create_executor() -> StandardPhaseExecutor:
    return StandardPhaseExecutor(SemanticPhase.REFLECT)
