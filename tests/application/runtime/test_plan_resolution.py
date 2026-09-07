"""Behavioral tests for ``lca.application.runtime.plan_resolution`` (PR-0199-P1-07).

Tests mock ``resolve_profile`` and ``compile_plan`` so they do NOT require
a real profile file on disk. They also patch ``compiled_run_plan_ref``
and ``declarative_plan_hash`` inside the service module because the test
stubs are deliberately minimal — the service's job is to compose the
three refs, not to recompute them.

Invariants covered:
  I-HPC-2 — CompiledRunPlan is treated as immutable (read-only).
  I-HPC-3 — refs are stable identifiers used to derive activation_ref.
  C8      — same profile_path ⇒ same refs regardless of session_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lca.application.runtime.plan_resolution import (
    PlanResolutionError,
    PlanResolutionResult,
    PlanResolutionService,
)
from lca.harness.composition.plan_compiler import (
    CompileOptions,
    PlanCompilerError,
)
from lca.harness.profile.resolve.resolve import resolve_profile as _real_resolve_profile

# ── Stubs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _StubPhaseGraph:
    """Minimal phase_graph-shaped stub for hashing."""

    entry: str = "perceive.main"
    nodes: tuple = ()
    edges: tuple = ()


@dataclass(frozen=True, slots=True)
class _StubPluginSpec:
    """Minimal plugin_spec-shaped stub."""

    id: str = "stub.plugin"


@dataclass(frozen=True, slots=True)
class _StubCompiledRunPlan:
    """Minimal CompiledRunPlan stub (service reads ``profile_path`` + ``phase_graph`` + ``plugin_specs``)."""

    profile_path: str = "/abs/profiles/x.yaml"
    phase_graph: Any | None = None
    plugin_specs: tuple = ()


@dataclass(frozen=True, slots=True)
class _StubResolvedProfile:
    """Minimal ResolvedProfile stub (returned by the mocked resolve_profile)."""

    profile_path: str = "/abs/profiles/x.yaml"


def _plan(profile_path: str = "/abs/profiles/x.yaml") -> _StubCompiledRunPlan:
    return _StubCompiledRunPlan(profile_path=profile_path)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def stub_plan() -> _StubCompiledRunPlan:
    return _plan()


@pytest.fixture
def stub_resolved() -> _StubResolvedProfile:
    return _StubResolvedProfile()


# ── Helpers ────────────────────────────────────────────────────────────────


def _patch_harness_layer(
    *,
    plan: Any,
    resolved: Any,
    resolve_side_effect: Any = None,
    compile_side_effect: Any = None,
    plan_ref: str = "plan-ref-test",
    graph_ref: str = "graph-ref-test",
    plugin_set_ref: str = "plugin-set-ref-test",
):
    """Patch the three harness symbols the service consumes.

    The service reads ``compiled_run_plan_ref`` + ``declarative_plan_hash``
    so we pin those to deterministic strings here — the hash algorithm is
    owned by ``lca.harness.plan`` and tested in isolation (see
    ``tests/harness/runtime/test_activation_ref.py``). The hash mock is
    a pure function: hashing ``plan.phase_graph`` always returns
    ``graph_ref``; hashing ``plan.plugin_specs`` always returns
    ``plugin_set_ref`` (same input ⇒ same output, C8).
    """
    resolve_patcher = patch(
        "lca.application.runtime.plan_resolution.resolve_profile",
        side_effect=resolve_side_effect,
        return_value=resolved if resolve_side_effect is None else None,
    )
    compile_patcher = patch(
        "lca.application.runtime.plan_resolution.compile_plan",
        side_effect=compile_side_effect,
        return_value=plan if compile_side_effect is None else None,
    )
    hash_patcher = patch(
        "lca.application.runtime.plan_resolution.compiled_run_plan_ref",
        return_value=plan_ref,
    )

    def _declarative_hash(value: object) -> str:
        # Stable mapping: phase_graph input ⇒ graph_ref; else ⇒ plugin_set_ref.
        if value is plan.phase_graph:
            return graph_ref
        return plugin_set_ref

    declarative_hash_patcher = patch(
        "lca.application.runtime.plan_resolution.declarative_plan_hash",
        side_effect=_declarative_hash,
    )
    resolve_patcher.start()
    compile_patcher.start()
    hash_patcher.start()
    declarative_hash_patcher.start()
    return (
        resolve_patcher,
        compile_patcher,
        hash_patcher,
        declarative_hash_patcher,
    )


# ── Happy path ─────────────────────────────────────────────────────────────


class TestResolveRefsHappyPath:
    def test_resolve_refs_returns_three_refs_and_plan(self, stub_plan, stub_resolved) -> None:
        """Happy path: returns (plan_ref, graph_ref, plugin_set_ref, plan)."""
        patches = _patch_harness_layer(plan=stub_plan, resolved=stub_resolved)
        try:
            result = PlanResolutionService().resolve_refs(stub_plan.profile_path)
        finally:
            for p in patches:
                p.stop()

        assert isinstance(result, PlanResolutionResult)
        assert result.plan_ref == "plan-ref-test"
        assert result.graph_ref == "graph-ref-test"
        assert result.plugin_set_ref == "plugin-set-ref-test"
        assert result.compiled_plan is stub_plan

    def test_resolve_refs_passes_profile_path_as_path(self, stub_plan, stub_resolved) -> None:
        """The service normalizes the input to ``Path`` before calling resolve."""
        resolve_mock = MagicMock(return_value=stub_resolved)
        compile_mock = MagicMock(return_value=stub_plan)

        def _hash(value: object) -> str:
            return "graph-ref" if value is stub_plan.phase_graph else "plugin-set-ref"

        with (
            patch(
                "lca.application.runtime.plan_resolution.resolve_profile",
                resolve_mock,
            ),
            patch(
                "lca.application.runtime.plan_resolution.compile_plan",
                compile_mock,
            ),
            patch(
                "lca.application.runtime.plan_resolution.compiled_run_plan_ref",
                return_value="plan-ref",
            ),
            patch(
                "lca.application.runtime.plan_resolution.declarative_plan_hash",
                side_effect=_hash,
            ),
        ):
            PlanResolutionService().resolve_refs("/abs/profiles/x.yaml")

        (path_arg,), _ = resolve_mock.call_args
        assert isinstance(path_arg, Path)
        assert str(path_arg) == "/abs/profiles/x.yaml"

    def test_resolve_refs_passes_compile_options(self, stub_plan, stub_resolved) -> None:
        """``compile_options`` configured at construction is forwarded to compile_plan."""
        from lca.contracts.atoms.scope.scope import Scope

        opts = CompileOptions(lifecycle=Scope.RUN)
        resolve_mock = MagicMock(return_value=stub_resolved)
        compile_mock = MagicMock(return_value=stub_plan)

        def _hash(value: object) -> str:
            return "graph-ref" if value is stub_plan.phase_graph else "plugin-set-ref"

        with (
            patch(
                "lca.application.runtime.plan_resolution.resolve_profile",
                resolve_mock,
            ),
            patch(
                "lca.application.runtime.plan_resolution.compile_plan",
                compile_mock,
            ),
            patch(
                "lca.application.runtime.plan_resolution.compiled_run_plan_ref",
                return_value="plan-ref",
            ),
            patch(
                "lca.application.runtime.plan_resolution.declarative_plan_hash",
                side_effect=_hash,
            ),
        ):
            PlanResolutionService(compile_options=opts).resolve_refs("/abs/profiles/x.yaml")

        # compile_plan was called exactly once with the configured options.
        compile_mock.assert_called_once()
        _, kwargs = compile_mock.call_args
        assert kwargs.get("options") is opts


# ── Error wrapping ─────────────────────────────────────────────────────────


class TestResolveRefsErrorWrapping:
    def test_resolve_refs_wraps_plan_compiler_error(self, stub_resolved) -> None:
        """``PlanCompilerError`` from compile_plan → ``PlanResolutionError``."""
        compile_err = PlanCompilerError("bad profile")
        patches = _patch_harness_layer(
            plan=None,
            resolved=stub_resolved,
            compile_side_effect=compile_err,
        )
        try:
            with pytest.raises(PlanResolutionError) as exc_info:
                PlanResolutionService().resolve_refs("/abs/profiles/x.yaml")
        finally:
            for p in patches:
                p.stop()

        # Original cause is preserved via ``raise from``.
        assert exc_info.value.__cause__ is compile_err
        assert "plan compile failed" in str(exc_info.value)

    def test_resolve_refs_wraps_resolve_error(self, stub_plan) -> None:
        """``FileNotFoundError`` from resolve → ``PlanResolutionError``."""
        resolve_err = FileNotFoundError("missing.yaml")
        patches = _patch_harness_layer(
            plan=stub_plan,
            resolved=None,
            resolve_side_effect=resolve_err,
        )
        try:
            with pytest.raises(PlanResolutionError) as exc_info:
                PlanResolutionService().resolve_refs("/abs/profiles/missing.yaml")
        finally:
            for p in patches:
                p.stop()

        assert exc_info.value.__cause__ is resolve_err
        assert "resolve_profile failed" in str(exc_info.value)


# ── Result / Service shape ─────────────────────────────────────────────────


class TestResultImmutability:
    def test_resolve_refs_result_is_frozen(self, stub_plan, stub_resolved) -> None:
        """``PlanResolutionResult`` is ``frozen=True, slots=True``."""
        patches = _patch_harness_layer(plan=stub_plan, resolved=stub_resolved)
        try:
            result = PlanResolutionService().resolve_refs(stub_plan.profile_path)
        finally:
            for p in patches:
                p.stop()

        with pytest.raises((AttributeError, Exception)):
            result.plan_ref = "mutated"  # type: ignore[misc]

    def test_service_is_constructable_with_no_options(self) -> None:
        """Construction without options is accepted (compile uses defaults)."""
        service = PlanResolutionService()
        assert service is not None

    def test_service_accepts_compile_options_at_construction(self) -> None:
        """``compile_options`` is stored at construction (forwarded in happy path)."""
        opts = CompileOptions()
        service = PlanResolutionService(compile_options=opts)
        assert service is not None


# ── C8 determinism ─────────────────────────────────────────────────────────


class TestC8Determinism:
    def test_session_id_does_not_affect_refs(self, stub_plan, stub_resolved) -> None:
        """``session_id`` is accepted but MUST NOT influence refs (C8)."""
        patches = _patch_harness_layer(plan=stub_plan, resolved=stub_resolved)
        try:
            result_a = PlanResolutionService().resolve_refs(
                stub_plan.profile_path, session_id="sess-A"
            )
            result_b = PlanResolutionService().resolve_refs(
                stub_plan.profile_path, session_id="sess-B"
            )
            result_none = PlanResolutionService().resolve_refs(stub_plan.profile_path)
        finally:
            for p in patches:
                p.stop()

        assert result_a.plan_ref == result_b.plan_ref == result_none.plan_ref
        assert result_a.graph_ref == result_b.graph_ref == result_none.graph_ref
        assert result_a.plugin_set_ref == result_b.plugin_set_ref == result_none.plugin_set_ref

    def test_same_profile_yields_stable_refs_across_calls(self, stub_plan, stub_resolved) -> None:
        """Same profile_path + same plan ⇒ same refs across N calls (C8 idempotent)."""
        patches = _patch_harness_layer(plan=stub_plan, resolved=stub_resolved)
        try:
            service = PlanResolutionService()
            results = [service.resolve_refs(stub_plan.profile_path) for _ in range(3)]
        finally:
            for p in patches:
                p.stop()

        plan_refs = {r.plan_ref for r in results}
        graph_refs = {r.graph_ref for r in results}
        plugin_refs = {r.plugin_set_ref for r in results}
        assert len(plan_refs) == 1
        assert len(graph_refs) == 1
        assert len(plugin_refs) == 1


# ── Sanity: the patched symbol really is what the module imports ───────────


def test_module_imports_real_symbols() -> None:
    """``PlanResolutionService`` resolves the real ``resolve_profile`` / ``compile_plan``."""
    # The module imports these symbols by name; verify the bindings are
    # exactly the canonical functions (no parallel shim).
    import lca.application.runtime.plan_resolution as mod

    assert mod.resolve_profile is _real_resolve_profile
    from lca.harness.composition import plan_compiler

    assert mod.compile_plan is plan_compiler.compile_plan
    assert mod.PlanCompilerError is plan_compiler.PlanCompilerError
