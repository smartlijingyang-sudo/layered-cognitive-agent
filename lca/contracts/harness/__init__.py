"""Harness SPI — core contracts for the LCA plugin-everything runtime.

This package defines the architectural contracts that the harness spine
is built upon. See ``docs/specs/harness-spine-spec.md`` for the full design.

Phase A scope: ``plugin.py``. Legacy ``PluginSpec`` adaptation lives in
``lca.harness.kernel.compat`` (contracts must not import implementations).
"""

from lca.contracts.harness.composer import (
    AgentGraph,
    Composer,
    TeamGraph,
    merge_agent_graphs,
)
from lca.contracts.harness.plugin_contract import (
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

__all__ = [
    "AgentGraph",
    "ArchitectureContract",
    "AuthorityContract",
    "CapabilityContract",
    "Composer",
    "EvidenceContract",
    "LifecycleContract",
    "OwnershipContract",
    "PluginContract",
    "PluginIdentity",
    "TeamGraph",
    "VerificationContract",
    "is_plugin_contract_empty",
    "merge_agent_graphs",
    "plugin_contract_control_slots",
    "plugin_contract_functional_group",
]
