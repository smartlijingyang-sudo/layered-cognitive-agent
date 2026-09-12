"""声明式计划契约的兼容导入门面。

ADR-0221: ``PhaseExecutor`` / ``PhaseContext`` / ``PhaseBinding`` /
``ControlEntry`` / ``PhaseContribution`` re-exports have been retired.
New code imports directly from ``declarative_1.declarative_graph`` and
``declarative_2.declarative_plugin``.
"""

from lca.contracts.protocols.act.command.envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    ALLOWED_EFFECTS,
    CARDINALITIES,
    DECLARATIVE_PLAN_VERSION,
    PLUGIN_SPEC_VERSION,
    DeclarativeValidationError,
    PluginSpecKind,
    RelationType,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    ActionAuthorityPlan,
    ActionScopeAuthority,
    CapabilityBinding,
    CognitivePhaseGraphPlan,
    EffectPolicyPlan,
    LoopGuard,
    PhaseEdge,
    PhaseExecutionPolicy,
    PhaseNode,
    PlanProvenance,
    ReplacementDecision,
    SubgraphReference,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    CapabilityDeclaration,
    EffectGovernanceDeclaration,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PluginConfiguration,
    PluginImplementation,
    PluginRelation,
    PluginSpec,
    VerificationDeclaration,
)

__all__ = [
    "ALLOWED_EFFECTS",
    "CARDINALITIES",
    "DECLARATIVE_PLAN_VERSION",
    "PLUGIN_SPEC_VERSION",
    "ActionAuthorityPlan",
    "ActionScopeAuthority",
    "CapabilityBinding",
    "CapabilityDeclaration",
    "CognitivePhaseGraphPlan",
    "CommandEnvelope",
    "DeclarativeValidationError",
    "EffectGovernanceDeclaration",
    "EffectPolicyPlan",
    "EvidenceDeclaration",
    "LifecycleDeclaration",
    "LoopGuard",
    "OwnershipDeclaration",
    "PhaseEdge",
    "PhaseExecutionPolicy",
    "PhaseNode",
    "PlanProvenance",
    "PluginConfiguration",
    "PluginImplementation",
    "PluginRelation",
    "PluginSpec",
    "PluginSpecKind",
    "RelationType",
    "ReplacementDecision",
    "RunDelta",
    "RunFact",
    "SemanticPhase",
    "SubgraphReference",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
    "VerificationDeclaration",
]
