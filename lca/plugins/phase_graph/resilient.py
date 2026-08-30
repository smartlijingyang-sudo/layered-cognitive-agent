"""Declarative provider for bounded phase-attempt fault tolerance."""

from __future__ import annotations

from typing import Literal

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


class PhaseAttemptPolicyConfig(BaseModel):
    """One JSON-ready execution policy compiled for a selected phase node."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    retry_on: tuple[Literal["timeout", "transient"], ...] = ()
    initial_backoff_seconds: float = Field(default=0.0, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1)
    on_exhausted: Literal["raise", "route_to_stop"] = "raise"


class Config(BaseModel):
    """Per-semantic-phase execution policies selected by a Profile or Bundle."""

    model_config = ConfigDict(extra="forbid")

    policies: dict[str, PhaseAttemptPolicyConfig] = Field(default_factory=dict)


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="phase.execution_policy.resilient",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="G5",
    implementation=PluginImplementation(
        module="lca.plugins.phase_graph.resilient",
        setup="setup",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.phase_graph.resilient.Config",
    ),
    provides=(
        CapabilityDeclaration(
            key="phase.execution_policy.resilient",
            cardinality="one",
            protocol="PhaseExecutionPolicyProvider",
            scope="profile",
        ),
    ),
    requires=(),
    effects=("none",),
    ownership=OwnershipDeclaration(
        reads=("profile.configuration",),
        emits=("phase.execution_policy.declared",),
        state_mutation="forbidden",
    ),
    lifecycle=LifecycleDeclaration(
        scopes=("profile", "run"),
        activation="true",
        disposal="required",
    ),
    relations=(),
    evidence=EvidenceDeclaration(
        emits=("PhaseExecutionPolicyDeclared",),
        replay="required",
    ),
    verification=VerificationDeclaration(
        test_suite="tests/declarative/test_phase_execution_policy.py",
        properties=("bounded_attempts", "timeout", "failure_route"),
    ),
)


@plugin(
    id="phase.execution_policy.resilient",
    Config=Config,
    provides=("phase.execution_policy.resilient",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_execution_policy.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Expose configuration for auditable capability closure; compilation reads the native spec."""

    if not isinstance(config, Config):
        raise TypeError("phase.execution_policy.resilient requires its declared Config")
    ctx.provide("phase.execution_policy.resilient", config.model_dump(mode="json"))


__all__ = ["SPEC", "Config", "PhaseAttemptPolicyConfig", "setup"]
