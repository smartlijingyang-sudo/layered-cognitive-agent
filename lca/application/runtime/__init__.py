"""Application-layer runtime services (ADR-0199 §2.1 L1).

This package owns the Application Services that wire the contracts layer
(lca.contracts.runtime) to the harness layer (lca.harness.profile.resolve
+ lca.harness.composition.plan_compiler). Per ADR-0199 §2.2.3 the
RuntimeFacade in this package is the unique consumer of RunIntent that
produces SessionActivation; L0 adapters (CLI/HTTP/test) MUST NOT call
resolve_profile or compile_plan directly.

Invariants:
  I-HPC-1 (入口薄) — only this facade consumes RunIntent.
  I-HPC-2 (Plan 不可变) — CompiledRunPlan referenced, never re-bound.
"""
