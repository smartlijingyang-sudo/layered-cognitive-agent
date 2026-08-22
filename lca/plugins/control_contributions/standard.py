"""Default declarative control-surface plugin for ADR-0074/0075.

The plugin is intentionally a single declarative provider: it makes every
standard control contribution visible to the Profile and the CompiledRunPlan.
It does not make policy decisions itself; the existing narrow executors retain
those behaviours behind independently addressable capability keys.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseContribution,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.control_contributions.act_authorize import ActAuthorizeExecutor
from lca.plugins.control_contributions.act_budget import ActBudgetExecutor
from lca.plugins.control_contributions.act_constrain import ActConstrainExecutor
from lca.plugins.control_contributions.act_execute import ActExecuteExecutor
from lca.plugins.control_contributions.act_safe_boundary import ActSafeBoundaryExecutor
from lca.plugins.control_contributions.observe_checkpoint import ObserveCheckpointExecutor
from lca.plugins.control_contributions.perceive_context import PerceiveContextExecutor
from lca.plugins.control_contributions.remember_admit import RememberAdmitExecutor
from lca.plugins.control_contributions.stop_decide import StopDecideExecutor
from lca.plugins.control_contributions.think_guard import ThinkGuardExecutor


class Config(BaseModel):
    """The standard control-surface has no runtime configuration."""

    model_config = ConfigDict(extra="forbid")


class ObserveWildcardExecutor:
    """Explicit no-op owner for the cross-cutting ``observe.*`` control slot."""

    async def execute(self, _context: object, _input: object):
        from lca.contracts.protocols.declarative_phase_graph import PhaseResult

        return PhaseResult(result_kind="control", payload={"verdict": "allow"})


_CONTROL_BINDINGS = (
    ("control.perceive.context", PerceiveContextExecutor, SemanticPhase.PERCEIVE, ContributionRole.GOVERN, "perceive.context"),
    ("control.think.guard", ThinkGuardExecutor, SemanticPhase.THINK, ContributionRole.GOVERN, "think.guard"),
    ("control.act.authorize", ActAuthorizeExecutor, SemanticPhase.ACT, ContributionRole.GOVERN, "act.authorize"),
    ("control.act.budget", ActBudgetExecutor, SemanticPhase.ACT, ContributionRole.GOVERN, "act.budget"),
    ("control.act.constrain", ActConstrainExecutor, SemanticPhase.ACT, ContributionRole.GOVERN, "act.constrain"),
    ("control.act.execute", ActExecuteExecutor, SemanticPhase.ACT, ContributionRole.GOVERN, "act.execute"),
    ("control.act.safe-boundary", ActSafeBoundaryExecutor, SemanticPhase.ACT, ContributionRole.GOVERN, "act.safe-boundary"),
    ("control.remember.admit", RememberAdmitExecutor, SemanticPhase.REMEMBER, ContributionRole.GOVERN, "remember.admit"),
    ("control.stop.decide", StopDecideExecutor, SemanticPhase.STOP, ContributionRole.GOVERN, "stop.decide"),
    ("control.observe.checkpoint", ObserveCheckpointExecutor, SemanticPhase.STOP, ContributionRole.OBSERVE, "observe.checkpoint"),
    ("control.observe.wildcard", ObserveWildcardExecutor, SemanticPhase.STOP, ContributionRole.OBSERVE, "observe.*"),
)


def _standard_spec() -> PluginSpec:
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id="control.contributions.standard",
        revision="1.0.0",
        kind=PluginSpecKind.PROVIDER,
        layer="L2",
        functional_group="G6",
        implementation=PluginImplementation(
            module="lca.plugins.control_contributions.standard", setup="setup"
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.control_contributions.standard.Config"
        ),
        provides=tuple(
            CapabilityDeclaration(
                key=capability,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            )
            for capability, _factory, _phase, _role, _slot in _CONTROL_BINDINGS
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=("state.view", "journal.cursor"),
            emits=tuple(f"control.{slot}" for *_prefix, slot in _CONTROL_BINDINGS),
            state_mutation="forbidden",
        ),
        lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=tuple(f"control.{slot}.verdict" for *_prefix, slot in _CONTROL_BINDINGS),
            replay="required",
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_control_contributions.py",
            properties=("control_slot_closure", "deny_on_any_deny", "no_state_mutation"),
        ),
        contributes=tuple(
            PhaseContribution(
                phase=phase,
                role=role,
                executor=capability,
                output=slot,
                order=index,
                aggregation="deny-on-any-deny" if role is ContributionRole.GOVERN else None,
            )
            for index, (capability, _factory, phase, role, slot) in enumerate(_CONTROL_BINDINGS)
        ),
    )


SPEC = _standard_spec()


@plugin(
    id="control.contributions.standard",
    Config=Config,
    provides=tuple(binding[0] for binding in _CONTROL_BINDINGS),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide every standard control executor through a plan-addressable key."""

    del config
    for capability, factory, _phase, _role, _slot in _CONTROL_BINDINGS:
        ctx.provide(capability, factory())


__all__ = ["SPEC", "Config", "ObserveWildcardExecutor", "setup"]
