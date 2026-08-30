"""标准 PhaseExecutor 插件的共享声明与无选择回退工具。"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)


class StandardPhaseConfig(BaseModel):
    """标准阶段执行器的显式空配置 schema。"""


def fallback_phase_result(
    *,
    phase: SemanticPhase,
    result_kind: str,
    input: PhaseInput,
) -> PhaseResult:
    """Build a no-op result without selecting or executing any phase behavior.

    Individual phase plugins choose their own result shape and call this helper
    only when their declared dependency is unavailable.  Keeping the helper
    generic prevents the shared module from becoming a second phase router.
    """

    return PhaseResult(
        result_kind=result_kind,
        payload={"phase": phase.value, "input": input.artifact},
    )


def standard_phase_spec(
    *,
    plugin_id: str,
    phase: SemanticPhase,
    module: str,
    effects: tuple[str, ...] = ("none",),
) -> PluginSpec:
    """Build the declarative specification for one independently provided phase."""

    capability = f"phase.{phase.value}.standard"
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id=plugin_id,
        revision="1.0.0",
        kind=PluginSpecKind.PHASE_EXECUTOR,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module=module, setup="setup", factory="create_executor"
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.phase_executors.common.StandardPhaseConfig"
        ),
        provides=(
            CapabilityDeclaration(
                key=capability,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            ),
        ),
        requires=(),
        effects=effects,
        ownership=OwnershipDeclaration(
            reads=("state.view", "journal.cursor"),
            emits=(f"phase.{phase.value}.result",),
            state_mutation="forbidden",
        ),
        lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=(f"Phase{phase.value.title()}Completed",), replay="required"
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_phase_graph.py",
            properties=("phase_result_contract", "no_state_mutation"),
        ),
        contributes=(
            PhaseContribution(
                phase=phase,
                role=ContributionRole.FINALIZE,
                executor=capability,
                output=f"phase.{phase.value}.result",
                order=0,
            ),
        ),
    )


__all__ = ["StandardPhaseConfig", "fallback_phase_result", "standard_phase_spec"]
