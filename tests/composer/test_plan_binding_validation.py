"""Plan binding must validate its declared capability surface before composition."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lca.contracts.protocols.perceive.capability_plan import ProviderBinding
from lca.plugins.composer.composition.plan_binding import BindPlanError, bind_plan


class _CountingComposer:
    """Fail the test if plan binding invokes composition before validation."""

    key = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def compose_agent(self, request: object, scope: object) -> object:
        del request, scope
        self.calls += 1
        raise AssertionError("plan binding must validate before composing an Agent graph")


class _Scope:
    """Minimal booted-scope double with explicit capability resolution records."""

    def __init__(self, composer: _CountingComposer) -> None:
        self._composer = composer
        self.injected: list[str] = []

    def inject(self, capability: str) -> object:
        self.injected.append(capability)
        if capability == "composer.counting":
            return self._composer
        raise KeyError(capability)


def _plan_with_missing_provider() -> object:
    """Build the minimum plan shape needed to exercise binding validation."""

    return SimpleNamespace(
        capability_bindings=(SimpleNamespace(capability="composer.counting"),),
        capability=SimpleNamespace(
            provider_bindings=(
                ProviderBinding(
                    capability="missing.registry[default]",
                    resolution_key="missing.registry",
                    owner_plugin="missing-provider",
                ),
            )
        ),
    )


def test_bind_plan_validates_declared_providers_before_invoking_composers() -> None:
    """A missing declared provider must fail before any graph contribution runs.

    The compiled plan is the source of truth for the runtime closure.  Checking
    it after composer dispatch allows partial construction and obscures whether
    a failure came from the plan or a composer implementation.
    """

    composer = _CountingComposer()
    scope = _Scope(composer)

    with pytest.raises(BindPlanError, match=r"missing\.registry"):
        bind_plan(MagicMock(), _plan_with_missing_provider(), scope=scope)

    assert composer.calls == 0
    assert "composer.counting" not in scope.injected


class _UnclassifiedComposer:
    """A misconfigured provider that does not implement either graph-composition Protocol."""

    key = "unclassified"


class _UnclassifiedScope:
    """Minimal scope that exposes one declared but invalid graph composer."""

    def inject(self, capability: str) -> object:
        if capability == "composer.unclassified":
            return _UnclassifiedComposer()
        raise KeyError(capability)


def test_bind_plan_rejects_a_composer_without_exactly_one_graph_protocol() -> None:
    """A graph-composer namespace entry must not be silently filtered out.

    The plan-binding seam owns the only transition from declared composition to
    a runnable graph.  Rejecting an unclassified provider here keeps failure
    locality at the profile declaration rather than at a later graph closure.
    """

    plan = SimpleNamespace(
        capability_bindings=(SimpleNamespace(capability="composer.unclassified"),),
        capability=SimpleNamespace(provider_bindings=()),
    )

    with pytest.raises(BindPlanError, match=r"composer\.unclassified.*exactly one"):
        bind_plan(MagicMock(), plan, scope=_UnclassifiedScope())


def test_binding_results_expose_composer_provenance_as_explicit_fields() -> None:
    """Binding results must keep their small public surface free of metadata bags.

    The binding seam exposes only one stable piece of diagnostic provenance:
    which plan-declared composer closed the graph.  A mutable ``dict[str, Any]``
    expands that interface without a named contract and lets unrelated callers
    add new facts at the most central composition boundary.
    """

    from dataclasses import fields

    from lca.plugins.composer.composition.plan_binding import PlanBindingResult, TeamBindingResult

    assert tuple(field.name for field in fields(PlanBindingResult)) == (
        "graph",
        "plan_ref",
        "plan",
        "composer_capabilities",
    )
    assert tuple(field.name for field in fields(TeamBindingResult)) == (
        "graph",
        "plan_ref",
        "plan",
        "composer_capability",
    )


def test_bind_plan_rejects_an_unresolvable_declared_composer_before_composition() -> None:
    """Every plan-declared composer is required, not an optional candidate.

    Silently skipping a missing ``composer.*`` capability lets a partial graph
    fail later with an implementation-shaped error.  The compiled plan must
    instead reject that configuration at the plan-binding seam, before any
    available composer is invoked.
    """

    composer = _CountingComposer()
    scope = _Scope(composer)
    plan = SimpleNamespace(
        capability_bindings=(
            SimpleNamespace(capability="composer.counting"),
            SimpleNamespace(capability="composer.missing"),
        ),
        capability=SimpleNamespace(provider_bindings=()),
    )

    with pytest.raises(BindPlanError, match=r"composer\.missing"):
        bind_plan(MagicMock(), plan, scope=scope)

    assert composer.calls == 0


class _ExplicitResolutionScope:
    """Scope double that records exact runtime keys requested by plan binding."""

    def __init__(self, composer: _CountingComposer) -> None:
        self._composer = composer
        self.injected: list[str] = []

    def inject(self, capability: str) -> object:
        self.injected.append(capability)
        if capability == "composer.counting":
            return self._composer
        if capability == "tools":
            return object()
        raise KeyError(capability)


def test_bind_plan_uses_the_provider_binding_resolution_key() -> None:
    """Provider validation resolves the compiled key, not a display selector.

    A capability name may carry a provider-specific selector for diagnostics,
    while the compiled plan names the exact scope seam.  Keeping that mapping in
    ``ProviderBinding`` makes the binding interface deep: composition need not
    parse registry syntax or know the tools namespace.
    """

    composer = _CountingComposer()
    scope = _ExplicitResolutionScope(composer)
    plan = SimpleNamespace(
        capability_bindings=(SimpleNamespace(capability="composer.counting"),),
        capability=SimpleNamespace(
            provider_bindings=(
                ProviderBinding(
                    capability="tools[restricted]",
                    resolution_key="tools",
                    owner_plugin="tools-provider",
                ),
            )
        ),
    )

    with pytest.raises(AssertionError, match="validate before composing"):
        bind_plan(MagicMock(), plan, scope=scope)

    assert scope.injected == ["tools", "composer.counting"]


def test_bind_plan_rejects_unavailable_explicit_resolution_key() -> None:
    """Plan binding must not infer registry or namespace fallbacks at runtime."""

    composer = _CountingComposer()
    scope = _ExplicitResolutionScope(composer)
    plan = SimpleNamespace(
        capability_bindings=(SimpleNamespace(capability="composer.counting"),),
        capability=SimpleNamespace(
            provider_bindings=(
                ProviderBinding(
                    capability="tools[restricted]",
                    resolution_key="tools[restricted]",
                    owner_plugin="tools-provider",
                ),
            )
        ),
    )

    with pytest.raises(BindPlanError, match=r"tools\[restricted\].*resolution key"):
        bind_plan(MagicMock(), plan, scope=scope)

    assert scope.injected == ["tools[restricted]"]
    assert composer.calls == 0
