"""标准 remember PhaseExecutor。"""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    StandardPhaseExecutor,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.remember.standard",
    phase=SemanticPhase.REMEMBER,
    module="lca.plugins.phase_executors.remember",
    effects=("memory",),
)


@plugin(
    id="phase.remember.standard",
    Config=StandardPhaseConfig,
    provides=("phase.remember.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.remember.standard", StandardPhaseExecutor(SemanticPhase.REMEMBER))


def create_executor() -> StandardPhaseExecutor:
    return StandardPhaseExecutor(SemanticPhase.REMEMBER)
