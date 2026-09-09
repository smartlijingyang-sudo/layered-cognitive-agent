"""Helper to build the PluginSpec for one flat think step plugin.

Lives in contracts so that the five step plugins (shortcut / route / reason /
classify / gate) can each declare ``PluginSpecKind.PHASE_EXECUTOR`` without
importing the temporary ``_shared.py`` glue module that this plan deletes.

After Task 4 removes the old ``_shared.py``, this helper remains as the
single source of PluginSpec construction for flat think step plugins.
"""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
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


def step_plugin_spec(*, plugin_id: str, module: str, test_suite: str) -> PluginSpec:
    """Build the PluginSpec for one flat think step plugin.

    All five flat step plugins share the same shape; only ``plugin_id``,
    ``module``, and ``test_suite`` vary.
    """
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id=plugin_id,
        revision="1.0.0",
        kind=PluginSpecKind.PHASE_EXECUTOR,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module=module,
            setup="setup",
            factory="create_executor",
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.loop.phase._shared.common.StandardPhaseConfig"
        ),
        provides=(
            CapabilityDeclaration(
                key=plugin_id,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            ),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=("state.view", "journal.cursor"),
            emits=("phase.think.result",),
            state_mutation="forbidden",
        ),
        lifecycle=LifecycleDeclaration(
            scopes=("run",), activation="true", disposal="required"
        ),
        relations=(),
        evidence=EvidenceDeclaration(emits=("PhaseThinkCompleted",), replay="required"),
        verification=VerificationDeclaration(
            test_suite=test_suite,
            properties=("phase_result_contract", "no_state_mutation"),
        ),
        contributes=(
            PhaseContribution(
                phase=SemanticPhase.THINK,
                role=ContributionRole.FINALIZE,
                executor=plugin_id,
                output="phase.think.result",
                order=0,
            ),
        ),
    )


__all__ = ["step_plugin_spec"]
