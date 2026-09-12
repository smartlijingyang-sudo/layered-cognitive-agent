"""Application Service — resolve_profile + compile_plan → refs (ADR-0199 P1-07).

Wraps the K1 (resolve_profile) and K2 (compile_plan) steps into one
Application Service so the RuntimeFacade (P1-09) and the wire adapters
(P1-08) have a single, testable seam. Per ADR-0199 I-HPC-2 the
CompiledRunPlan returned is treated as immutable; per I-HPC-3 the
returned refs are stable identifiers used to derive activation_ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.plan import compiled_run_plan_ref, declarative_plan_hash
from lca.harness.profile.resolve.resolve import (
    ResolvedProfile,
    resolve_profile,
)
from lca.harness.profile.validate.errors import ProfileResolveError
from lca_kernel.plan.plan_compile import (
    CompileOptions,
    PlanCompilerError,
    compile_plan,
)


@dataclass(frozen=True, slots=True)
class PlanResolutionResult:
    """Immutable result of PlanResolutionService.resolve_refs.

    Per ADR-0199 I-HPC-2 the CompiledRunPlan is a read-only reference;
    callers MUST NOT mutate it. The three refs (plan_ref / graph_ref /
    plugin_set_ref) are stable identifiers per ADR-0199 I-HPC-3 — they
    feed ``compute_activation_ref`` together with the session_id.
    """

    plan_ref: str
    graph_ref: str
    plugin_set_ref: str
    compiled_plan: CompiledRunPlan


class PlanResolutionError(RuntimeError):
    """Raised when resolve_profile or compile_plan fails.

    Wraps the underlying PlanCompilerError / ProfileResolveError so the
    facade can map them to a stable error contract (DOC-* codes). The
    original cause is preserved via ``raise ... from``.
    """


class PlanResolutionService:
    """Application Service that resolves a profile path to refs + plan.

    This service is the SINGLE entry point for converting a profile path
    into a CompiledRunPlan plus its three SSOT identifiers
    (``plan_ref`` / ``graph_ref`` / ``plugin_set_ref``). It does NOT
    boot a cordis Context, spawn a fiber, or call Session.append —
    those happen in the facade (P1-09) or the coordinator (existing
    RunLifecycleCoordinator).
    """

    def __init__(
        self,
        *,
        compile_options: CompileOptions | None = None,
    ) -> None:
        # ``CompileOptions`` is itself frozen; storing the reference is
        # enough to guarantee it is never mutated by callers.
        self._compile_options = compile_options

    def resolve_refs(
        self,
        profile_path: str | Path,
        *,
        session_id: str | None = None,
    ) -> PlanResolutionResult:
        """Resolve a profile path → ResolvedProfile → CompiledRunPlan.

        Per ADR-0199 P1-07 spec: returns the three SSOT refs plus the
        immutable plan. ``session_id`` is accepted (not yet used;
        reserved for future profile variants that key on session) but
        MUST NOT affect determinism of the refs (C8): the same
        ``profile_path`` yields the same ``plan_ref`` / ``graph_ref`` /
        ``plugin_set_ref`` regardless of ``session_id``.
        """
        del session_id  # accepted for future use; not consumed by K1+K2
        path = Path(profile_path)
        try:
            resolved: ResolvedProfile = resolve_profile(path)
            plan: CompiledRunPlan = compile_plan(resolved, options=self._compile_options)
        except PlanCompilerError as exc:
            raise PlanResolutionError(f"plan compile failed: {exc}") from exc
        except ProfileResolveError as exc:
            raise PlanResolutionError(f"resolve_profile failed: {exc}") from exc
        except (FileNotFoundError, ValueError, TypeError) as exc:
            # resolve_profile surfaces file/value/type errors directly
            # when adapters mis-format input; wrap them so the facade has
            # one stable error contract.
            raise PlanResolutionError(f"resolve_profile failed: {exc}") from exc

        plan_ref = compiled_run_plan_ref(plan)
        # graph_ref / plugin_set_ref are derived from immutable plan
        # regions; both are stable hashes over canonical JSON (I-HPC-2:
        # the plan is read-only so the hashes are stable across reads).
        # ADR-0221 P3: in the v2 path, ``compile_plan`` returns a
        # ``V2ExecutablePlan`` wrapper whose ``.inner`` is the immutable
        # ``CompiledRunPlan`` (no ``phase_graph`` region); the v2 graph
        # spec travels under ``.graph_spec``. Unwrap uniformly so the
        # three SSOT refs remain deterministic across v1/v2.
        inner = getattr(plan, "inner", plan)
        graph_input = getattr(plan, "graph_spec", None)
        if graph_input is None:
            graph_input = getattr(inner, "phase_graph", None)
        plugin_input = getattr(inner, "plugin_specs", ())
        graph_ref = declarative_plan_hash(graph_input)
        plugin_set_ref = declarative_plan_hash(plugin_input)

        return PlanResolutionResult(
            plan_ref=plan_ref,
            graph_ref=graph_ref,
            plugin_set_ref=plugin_set_ref,
            compiled_plan=plan,
        )


__all__ = (
    "PlanResolutionError",
    "PlanResolutionResult",
    "PlanResolutionService",
)
