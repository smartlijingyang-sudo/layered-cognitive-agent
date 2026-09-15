"""HISTORY: bounded recovery phase-edge provider (ADR-0075) — retired as edge SSOT.

M1 (Issue #14, 2026-09-15): ControlPlan recovery edges live ONLY on
``bundles/outer/phase_main.yaml``. Reflect nodes emit routing hints;
this plugin must NOT register a second ``phase.edge.recovery`` capability.

delete-when: 2026-10-15 — remove this module once no profile/bundle entry
activates ``phase.edge.reflect_to_think.recovery`` and the anti-backfill
profile contract remains green.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    CapabilityDeclaration,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    VerificationDeclaration,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,  # noqa: F811
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class RecoveryLoopConfig(BaseModel):
    """Bounded re-entry policy (retained for schema compatibility only)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    max_iterations: int = Field(default=1, alias="maxIterations")
    budget: str = "run.steps"
    terminal_predicate: str = Field(
        default="not result.next_hints.admit_recovery",
        alias="terminalPredicate",
    )


class RecoveryEdgeConfig(BaseModel):
    """Legacy config shape — ignored; setup is a no-op (M1)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source: str = "reflect.main"
    target: str = "think.main"
    when: str = "result.next_hints.admit_recovery"
    loop: RecoveryLoopConfig = Field(default_factory=RecoveryLoopConfig)


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.edge.reflect_to_think.recovery",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="G5",
    implementation=PluginImplementation(
        module="lca.plugins.loop.graph.recovery.plugin",
        setup="setup",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.loop.graph.recovery.plugin.RecoveryEdgeConfig",
    ),
    # M1: do not declare PhaseEdge capability — outer YAML is sole edge SSOT.
    provides=(),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(state_mutation="forbidden"),
    lifecycle=LifecycleDeclaration(
        scopes=("profile", "run"), activation="true", disposal="required"
    ),
    relations=(),
    evidence=EvidenceDeclaration(emits=(), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/lca_kernel/boot/test_m1_edge_ssot_backfill.py",
        properties=("m1_no_second_recovery_edge_capability",),
    ),
)


@plugin(
    id="phase.edge.reflect_to_think.recovery",
    Config=RecoveryEdgeConfig,
    provides=(),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/lca_kernel/boot/test_m1_edge_ssot_backfill.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_edge_reflect_to_think_recovery.checked",
                "phase_edge_reflect_to_think_recovery.served",
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
async def setup(ctx: PluginContext, config: RecoveryEdgeConfig) -> None:
    """M1 no-op: do not ``provide(\"phase.edge.recovery\")``.

    Outer ``bundles/outer/phase_main.yaml`` owns the admit_recovery edge.
    Activating this plugin must not reintroduce a second ControlPlan edge source.
    delete-when: 2026-10-15
    """
    del ctx, config


__all__ = ["SPEC", "RecoveryEdgeConfig", "RecoveryLoopConfig", "setup"]
