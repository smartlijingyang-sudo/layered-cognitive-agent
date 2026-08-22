"""标准 act PhaseExecutor。"""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    StandardPhaseExecutor,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.act.standard",
    phase=SemanticPhase.ACT,
    module="lca.plugins.phase_executors.act",
)


@plugin(
    id="phase.act.standard",
    Config=StandardPhaseConfig,
    provides=("phase.act.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.act.standard", StandardPhaseExecutor(SemanticPhase.ACT))


def create_executor() -> StandardPhaseExecutor:
    return StandardPhaseExecutor(SemanticPhase.ACT)
