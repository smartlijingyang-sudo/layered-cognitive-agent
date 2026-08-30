"""Harness SPI — core contracts for the LCA plugin-everything runtime.

This package defines the architectural contracts that the harness spine
is built upon. See ``docs/specs/harness-spine-spec.md`` for the full design.

Phase A scope: ``plugin.py``. Legacy ``PluginSpec`` adaptation lives in
``lca.harness.kernel.compat`` (contracts must not import implementations).
"""

from lca.contracts.harness.composition.composer import (
    AgentGraph,
    AgentGraphComposer,
    AgentGraphContribution,
    TeamGraph,
    TeamGraphComposer,
    merge_agent_graphs,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    CapabilityContract,
    EvidenceContract,
    LifecycleContract,
    OwnershipContract,
    PluginContract,
    PluginIdentity,
    VerificationContract,
    is_plugin_contract_empty,
    plugin_contract_control_slots,
    plugin_contract_functional_group,
)
from lca.contracts.harness.journal.artifact import (
    ArtifactController,
    CapabilityArtifact,
    InvalidStateTransitionError,
    artifact_with_state,
    capability_artifact_to_dict,
    is_terminal_state,
    legal_next_states,
    make_capability_artifact,
    migrate_artifact,
    migrate_to_active,
    migrate_to_retired,
    migrate_to_verified,
)
from lca.contracts.harness.tasks.continuous import (
    ContinuousControlPlane,
    ContinuousControlPlaneFactory,
    SessionWorkActivator,
    Trigger,
    TriggerKind,
    WorkActivationReceipt,
    WorkItem,
    WorkLease,
    WorkQueue,
    WorkStatus,
)

__all__ = [
    "AgentGraph",
    "AgentGraphComposer",
    "AgentGraphContribution",
    "ArchitectureContract",
    "ArtifactController",
    "AuthorityContract",
    "CapabilityArtifact",
    "CapabilityContract",
    "ContinuousControlPlane",
    "ContinuousControlPlaneFactory",
    "EvidenceContract",
    "InvalidStateTransitionError",
    "LifecycleContract",
    "OwnershipContract",
    "PluginContract",
    "PluginIdentity",
    "SessionWorkActivator",
    "TeamGraph",
    "TeamGraphComposer",
    "Trigger",
    "TriggerKind",
    "VerificationContract",
    "WorkActivationReceipt",
    "WorkItem",
    "WorkLease",
    "WorkQueue",
    "WorkStatus",
    "artifact_with_state",
    "capability_artifact_to_dict",
    "is_plugin_contract_empty",
    "is_terminal_state",
    "legal_next_states",
    "make_capability_artifact",
    "merge_agent_graphs",
    "migrate_artifact",
    "migrate_to_active",
    "migrate_to_retired",
    "migrate_to_verified",
    "plugin_contract_control_slots",
    "plugin_contract_functional_group",
]
