"""Runtime contracts — L1 Facade + RunIntent + SessionActivation (ADR-0199 §2.2).

This package owns the wire-agnostic types that any L0 surface (CLI / HTTP /
test / batch / gateway / IDE) must use to talk to the single RuntimeFacade
port. See ADR-0199 §2.1 for the L0→L1 boundary contract and §2.2 for the
specific shapes.

Invariants:
  I-HPC-1 (入口薄) — L0 only produces RunIntent; never resolves profile
                      or compiles a plan directly.
  I-HPC-2 (Plan 不可变) — CompiledRunPlan is referenced, never re-bound.
  I-HPC-3 (Activation 绑定) — durable events carry activation_ref.
  I-HPC-4 (声明先于执行) — TrustEnvelope.granted_privileges is checked
                            against EffectPolicyPlan.
  I-HPC-11 (信任默认拒绝) — untrusted PluginOrigin is default disabled.
"""

from __future__ import annotations

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.external_plugin import (
    DEFAULT_EXTERNAL_KIND_BY_TRUST,
    ExternalPluginKind,
    default_external_kind,
    is_high_isolation_kind,
    is_sandbox_kind,
)
from lca.contracts.runtime.facade import RunHandle, RuntimeFacade
from lca.contracts.runtime.intent import RunIntent, RunMode, RunSurface
from lca.contracts.runtime.plan_proposal import (
    PlanProposal,
    ProposalStatus,
    build_proposal,
    compute_proposal_ref,
)
from lca.contracts.runtime.resource import (
    RESERVED_NAMESPACES,
    ResourceId,
    ResourceKind,
)
from lca.contracts.runtime.trust import (
    EMPTY_TRUST_ENVELOPE,
    PluginOrigin,
    PluginSource,
    PluginTrustLevel,
    TrustEnvelope,
)

__all__ = (  # noqa: RUF022  sorted() order is enforced by test_runtime_package_exports::test_all_is_sorted
    "DEFAULT_EXTERNAL_KIND_BY_TRUST",
    "EMPTY_TRUST_ENVELOPE",
    "ExternalPluginKind",
    "PlanProposal",
    "PluginOrigin",
    "PluginSource",
    "PluginTrustLevel",
    "ProposalStatus",
    "RESERVED_NAMESPACES",
    "ResourceId",
    "ResourceKind",
    "RunHandle",
    "RunIntent",
    "RunMode",
    "RunSurface",
    "RuntimeFacade",
    "SessionActivation",
    "TrustEnvelope",
    "build_proposal",
    "compute_proposal_ref",
    "default_external_kind",
    "is_high_isolation_kind",
    "is_sandbox_kind",
)
