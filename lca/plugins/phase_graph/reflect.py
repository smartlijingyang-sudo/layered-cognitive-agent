"""标准 reflect PhaseExecutor。

在标准失败检测模式下:当 observation 不存在或 observation.success 为 False 时,
输出 `admit_recovery = True`,允许 recovery profile 触发 reflect → think 重入边。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_graph.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_graph.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.reflect.standard",
    phase=SemanticPhase.REFLECT,
    module="lca.plugins.phase_graph.reflect",
)


@dataclass(frozen=True, slots=True)
class StandardReflectExecutor:
    """Create reflection from the act artifact through the selected Brain."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        brain = StandardPhaseCapabilities(context.capabilities).brain
        observation = cast("Observation | None", context.artifacts.get("act"))
        if brain is None or observation is None:
            return fallback_phase_result(
                phase=SemanticPhase.REFLECT,
                result_kind="reflection",
                input=input,
            )
        return PhaseResult(
            result_kind="reflection",
            payload=await brain.reflect(context.state, observation),
        )


@dataclass(frozen=True, slots=True)
class RecoveryReflectExecutor:
    """Decorate standard reflection with declarative recovery-routing metadata."""

    def _is_failure(self, observation: object) -> bool:
        if observation is None:
            return True
        if isinstance(observation, Mapping):
            success = observation.get("success")
            return success is False or success is None
        return getattr(observation, "success", None) is False

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        observation = context.artifacts.get("act")
        base_result = await StandardReflectExecutor().execute(context, input)
        return PhaseResult(
            result_kind=base_result.result_kind,
            facts=base_result.facts,
            deltas=base_result.deltas,
            evidence_refs=base_result.evidence_refs,
            next_hints={
                **dict(base_result.next_hints),
                "admit_recovery": self._is_failure(observation),
            },
            payload=base_result.payload,
            command_envelope=base_result.command_envelope,
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_reflect_standard.checked", "phase_reflect_standard.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.reflect.standard", RecoveryReflectExecutor())


def create_executor() -> RecoveryReflectExecutor:
    return RecoveryReflectExecutor()


__all__ = ["RecoveryReflectExecutor", "StandardReflectExecutor", "create_executor"]
