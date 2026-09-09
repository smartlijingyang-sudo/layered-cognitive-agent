"""phase.think.classify — convert LLMResponse to Decision via DecisionClassifier."""

from __future__ import annotations

from dataclasses import dataclass, replace

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.plugins.think.step_plugin_spec import step_plugin_spec
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

STAGE_KIND = "think_stage"

SPEC = step_plugin_spec(
    plugin_id="phase.think.classify",
    module="lca.plugins.think.classify.plugin",
    test_suite="tests/think/test_classify_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkClassifyExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        if carry.response is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        classifier = context.capabilities.get("phase.think.classify")
        if classifier is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(classifier, DecisionClassifier), (  # noqa: S101 - C5 typed capability contract check
            "phase.think.classify must implement DecisionClassifier"
        )
        decision = classifier.classify(carry.response)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, decision=decision),
        )


@plugin(
    id="phase.think.classify",
    Config=StandardPhaseConfig,
    provides=("phase.think.classify",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_classify_phase_plugin.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_classify.checked",
                "phase_think_classify.served",
            )
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
    del config
    ctx.provide("phase.think.classify", ThinkClassifyExecutor())


def create_executor() -> ThinkClassifyExecutor:
    return ThinkClassifyExecutor()


__all__ = ["ThinkClassifyExecutor", "create_executor", "setup"]
