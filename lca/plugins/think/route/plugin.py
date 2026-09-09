"""phase.think.route — SkillRouter picks active template; Reducer folds state."""

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
from lca.contracts.protocols import SkillRouter
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

STAGE_KIND = "think_stage"


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkRouteExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        router = context.capabilities.get("phase.think.route")
        if router is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(router, SkillRouter), (  # noqa: S101 - C5 typed capability contract check
            "phase.think.route must implement SkillRouter"
        )
        reducer = context.capabilities.get("phase.think.reducer")
        if reducer is None:
            raise RuntimeError(
                "phase.think.route requires phase.think.reducer when a SkillRouter is configured"
            )
        apply_skill_route = getattr(reducer, "apply_skill_route", None)
        if not callable(apply_skill_route):
            raise RuntimeError(
                "phase.think.reducer must expose apply_skill_route(state, active_template)"
            )
        active_template = await router.route(carry.state)
        routed_state = apply_skill_route(carry.state, active_template)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, state=routed_state),
        )


@plugin(
    id="phase.think.route",
    Config=StandardPhaseConfig,
    provides=("phase.think.route",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_route_phase_plugin.py",
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
                "phase_think_route.checked",
                "phase_think_route.served",
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
    ctx.provide("phase.think.route", ThinkRouteExecutor())


def create_executor() -> ThinkRouteExecutor:
    return ThinkRouteExecutor()


__all__ = ["ThinkRouteExecutor", "create_executor", "setup"]
