"""Tests for the private ``_unwrap_v2`` helper.

ADR-0221 P3 collapses v1 (``CompiledRunPlan``) and v2 (``V2ExecutablePlan``)
plan shapes through a single unwrap seam so plan_ref hashing, the to_dict
projection, and CLI introspection see the same v1-shaped view. Two
duplicate ``hasattr(plan, "inner") and hasattr(plan, "graph_spec")``
probes lived in ``lca.harness.plan`` before this helper landed; these
tests pin the contract so a third accidental copy does not regress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.plan import (
    _unwrap_v2,
    compiled_run_plan_ref,
    compiled_run_plan_to_dict,
)


@dataclass(frozen=True, slots=True)
class _FakeV2Wrapper:
    """Stand-in for ``V2ExecutablePlan`` exposing the same duck shape.

    The real wrapper is in ``lca_kernel.plan.plan_compile`` and cannot be
    referenced here (it would create a circular import for the very reason
    ``_unwrap_v2`` stays duck-typed). The shape contract is what matters.
    """

    inner: CompiledRunPlan
    graph_spec: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _HalfWrapper:
    """A v2-ish object missing ``graph_spec`` — must NOT unwrap."""

    inner: Any = None


@dataclass(frozen=True, slots=True)
class _GraphOnly:
    """A v2-ish object missing ``inner`` — must NOT unwrap."""

    graph_spec: dict = field(default_factory=dict)


class TestUnwrapV2:
    def test_v1_plan_returned_unchanged(self) -> None:
        """``CompiledRunPlan`` (v1) has no ``inner``/``graph_spec``; pass through."""
        v1 = _build_v1_plan()
        assert _unwrap_v2(v1) is v1

    def test_v2_wrapper_unwrapped_to_inner(self) -> None:
        """V2 wrapper exposes ``inner`` + ``graph_spec``; helper returns ``inner``."""
        inner = _build_v1_plan()
        wrapper = _FakeV2Wrapper(inner=inner, graph_spec={"nodes": [], "edges": []})
        assert _unwrap_v2(wrapper) is inner

    def test_wrapper_without_graph_spec_is_passed_through(self) -> None:
        """Has ``inner`` but no ``graph_spec`` — not a v2 wrapper, pass through."""
        sentinel = _HalfWrapper(inner="not-a-plan")
        assert _unwrap_v2(sentinel) is sentinel

    def test_wrapper_without_inner_is_passed_through(self) -> None:
        """Has ``graph_spec`` but no ``inner`` — not a v2 wrapper, pass through."""
        sentinel = _GraphOnly(graph_spec={"nodes": [], "edges": []})
        assert _unwrap_v2(sentinel) is sentinel


class TestUnwrapV2IntegrationWithPlanRef:
    """Both unwrap call sites — ``compiled_run_plan_ref`` and
    ``compiled_run_plan_to_dict`` — must agree that a v2 wrapper hashes
    identically to its inner plan. This pins the seam against future
    drift between the two projections."""

    def test_plan_ref_stable_across_v1_and_v2_shape(self) -> None:
        inner = _build_v1_plan()
        wrapper = _FakeV2Wrapper(inner=inner, graph_spec={"nodes": [], "edges": []})
        assert compiled_run_plan_ref(inner) == compiled_run_plan_ref(wrapper)

    def test_to_dict_uses_inner_payload_even_when_wrapper_supplied(self) -> None:
        inner = _build_v1_plan()
        wrapper = _FakeV2Wrapper(inner=inner, graph_spec={"nodes": [], "edges": []})
        inner_dict = compiled_run_plan_to_dict(inner)
        wrapper_dict = compiled_run_plan_to_dict(wrapper)
        assert inner_dict == wrapper_dict
        assert wrapper_dict["profile_path"] == inner.profile_path


# ── helpers ─────────────────────────────────────────────────────────


def _build_v1_plan() -> CompiledRunPlan:
    """Build a minimal ``CompiledRunPlan`` for unwrap seams.

    The plan only needs to satisfy ``CompiledRunPlan.__post_init__``;
    hashing and projection only read fields, never mutate.
    """
    from lca.contracts.atoms.scope.scope import Scope
    from lca.contracts.protocols.perceive.capability_plan import CapabilityPlan
    from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan

    capability = CapabilityPlan(
        profile_path="x.yaml",
        revision="v1",
        provider_bindings=(),
        relations=(),
    )
    scope = ScopePlan(
        profile_path="x.yaml",
        lifecycle=Scope.RUN,
        visibility=(Scope.RUN,),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
    )
    return CompiledRunPlan(
        profile_path="x.yaml",
        capability=capability,
        scope=scope,
    )
