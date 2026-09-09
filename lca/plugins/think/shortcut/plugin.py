"""phase.think.shortcut — try a deterministic shortcut before reason."""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.protocols import SupportsShortcut
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

SPEC = step_plugin_spec(
    plugin_id="phase.think.shortcut",
    module="lca.plugins.think.shortcut.plugin",
    test_suite="tests/think/test_shortcut_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkShortcutExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        cap = context.capabilities.get("phase.think.shortcut")
        if cap is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=_carry(context))
        assert isinstance(cap, SupportsShortcut), (  # noqa: S101 - C5 typed capability contract check
            "phase.think.shortcut must implement SupportsShortcut"
        )
        decision = await cap.try_shortcut(context.state)
        if decision is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=_carry(context))
        return PhaseResult(result_kind="decision", payload=decision)


@plugin(
    id="phase.think.shortcut",
    Config=StandardPhaseConfig,
    provides=("phase.think.shortcut",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_shortcut_phase_plugin.py",
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
                "phase_think_shortcut.checked",
                "phase_think_shortcut.served",
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
    ctx.provide("phase.think.shortcut", ThinkShortcutExecutor())


def create_executor() -> ThinkShortcutExecutor:
    return ThinkShortcutExecutor()


__all__ = ["ThinkShortcutExecutor", "create_executor", "setup"]
