"""Bounded recovery phase-edge provider for ADR-0075."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.protocols.declarative.declarative_phase_graph import (
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
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class RecoveryLoopConfig(BaseModel):
    """Bounded re-entry policy for one recovery edge."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    max_iterations: int = Field(default=1, alias="maxIterations")
    budget: str = "run.steps"
    terminal_predicate: str = Field(
        default="not result.next_hints.admit_recovery",
        alias="terminalPredicate",
    )


class RecoveryEdgeConfig(BaseModel):
    """Profile-selected reflect-to-think recovery edge."""

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
        module="lca.plugins.phase_edges.recovery",
        setup="setup",
    ),
    configuration=PluginConfiguration(schema="lca.plugins.phase_edges.recovery.RecoveryEdgeConfig"),
    provides=(
        CapabilityDeclaration(
            key="phase.edge.recovery",
            cardinality="one",
            protocol="PhaseEdge",
            scope="profile",
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(state_mutation="forbidden"),
    lifecycle=LifecycleDeclaration(
        scopes=("profile", "run"), activation="true", disposal="required"
    ),
    relations=(),
    evidence=EvidenceDeclaration(emits=("RecoveryEdgeDeclared",), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/declarative/test_recovery_edge.py",
        properties=("recovery_edge_contract", "bounded_reentry"),
    ),
)


@plugin(
    id="phase.edge.reflect_to_think.recovery",
    Config=RecoveryEdgeConfig,
    provides=("phase.edge.recovery",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_recovery_edge.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: RecoveryEdgeConfig) -> None:
    """Expose the selected recovery edge as immutable plan data."""
    ctx.provide(
        "phase.edge.recovery",
        {
            "source": config.source,
            "target": config.target,
            "when": config.when,
            "loop": {
                "max_iterations": config.loop.max_iterations,
                "budget": config.loop.budget,
                "terminal_predicate": config.loop.terminal_predicate,
            },
        },
    )


__all__ = ["SPEC", "RecoveryEdgeConfig", "RecoveryLoopConfig", "setup"]
