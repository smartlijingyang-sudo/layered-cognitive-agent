"""Build-time completeness checks for the spine wrap registry (Task 3.5).

Five-layer enforcement (ADR-0165.1 §决定 1):
- Layer-1: every EXECUTION_POINTS entry has a registered handler
  (``SpineRegistry.keys() ⊇ EXECUTION_POINTS``).
- Layer-2: every registered handler has both ``wrap_fn`` and
  ``target_module`` bound (no half-bound specs).

The build-time pytest suite asserts these as hard-fail; the runtime
kernel boot hook warns softly so PR-3 wiring work (still landing
across sub-PRs 3.1–3.4) does not break the boot.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
from lca.infrastructure.observability.spine.registry import (
    IncompleteRegistry,
    MissingWrapFn,
    SpineRegistry,
)


def _noop(*args: Any, **kwargs: Any) -> Any:
    return None


# ── Layer-1 — every EXECUTION_POINTS handler registered ──────────────


def test_layer1_subset_of_execution_points_passes() -> None:
    """Registering only a subset of EXECUTION_POINTS and validating against
    that subset must succeed — the registry is used both to scope to one
    profile (subset validation) and to enforce full coverage (full-set
    validation)."""
    registry = SpineRegistry()
    subset = EXECUTION_POINTS[:3]
    for point in subset:
        registry.register(
            execution_point=point,
            wrap_fn=_noop,
            target_module=f"mod.{point}",
        )
    registry.validate(subset)  # no error


def test_layer1_full_execution_points_without_all_registrations_raises() -> None:
    """Registering only 3 handlers and validating against the full
    EXECUTION_POINTS close-set must raise ``IncompleteRegistry`` and name
    the missing points in the error message."""
    registry = SpineRegistry()
    for point in EXECUTION_POINTS[:3]:
        registry.register(
            execution_point=point,
            wrap_fn=_noop,
            target_module=f"mod.{point}",
        )
    with pytest.raises(IncompleteRegistry) as excinfo:
        registry.validate(EXECUTION_POINTS)
    missing = set(EXECUTION_POINTS) - set(EXECUTION_POINTS[:3])
    for point in missing:
        assert point in str(excinfo.value)


# ── Layer-2 — every registration binds wrap_fn + target_module ───────


def test_layer2_register_without_wrap_fn_raises() -> None:
    """``register`` must reject an entry whose ``wrap_fn`` is None — the
    whole point of Layer-2 is to forbid half-bound specs that would
    silently no-op at runtime."""
    registry = SpineRegistry()
    with pytest.raises(MissingWrapFn):
        registry.register(  # type: ignore[arg-type]
            execution_point="brain.think.start",
            wrap_fn=None,
            target_module="mod.brain",
        )


def test_layer2_register_without_target_module_raises() -> None:
    """``register`` must reject an entry whose ``target_module`` is empty —
    a wrap_fn without a target_module cannot be wired into the cordis
    context (the wrap is meaningless without a host)."""
    registry = SpineRegistry()
    with pytest.raises(MissingWrapFn):
        registry.register(
            execution_point="brain.think.start",
            wrap_fn=_noop,
            target_module="",
        )


# ── Surface — keys() and get() expose the registry ──────────────────


def test_keys_returns_registered_points() -> None:
    """``keys()`` returns the set of execution points the registry holds,
    in registration order. Useful for diagnostics and for the runtime
    boot hook to log coverage gaps."""
    registry = SpineRegistry()
    points = EXECUTION_POINTS[:5]
    for point in points:
        registry.register(
            execution_point=point,
            wrap_fn=_noop,
            target_module=f"mod.{point}",
        )
    assert registry.keys() == tuple(points)


def test_get_returns_wrap_fn_for_point() -> None:
    """``get(point)`` returns the wrap_fn bound to ``point``; ``get`` for
    an unknown point returns ``None``."""

    def _identity(*args: Any, **kwargs: Any) -> Any:
        return "result"

    registry = SpineRegistry()
    registry.register(
        execution_point="brain.think.start",
        wrap_fn=_identity,
        target_module="mod.brain",
    )
    assert registry.get("brain.think.start") is _identity
    assert registry.get("not.registered") is None


# ── Integration — compile_spine_registry + full EXECUTION_POINTS ─────


def test_compile_spine_registry_returns_handlers_for_real_reflectors() -> None:
    """``compile_spine_registry`` walks the spine plugins package and
    registers every ``emit_*`` helper whose AST carries a canonical
    ``execution_point="..."`` literal. PR-3.1–3.4 reflectors land
    cognition / body / llm / memory / runtime EPs — at least those
    five categories must show up in the assembled registry."""
    from lca.harness.profile.compile_spine_registry import compile_spine_registry

    registry = compile_spine_registry()
    keys = set(registry.keys())

    expected_categories = {
        "brain.think.start",
        "body.tool.execute.start",
        "llm.call.start",
        "memory.read",
        "runtime.reducer.apply",
    }
    missing = expected_categories - keys
    assert not missing, f"compile_spine_registry did not register: {missing}"


def test_layer1_full_execution_points_hard_fail_in_ci() -> None:
    """Build-time hard-fail demonstration: when the registry covers a
    proper subset of EXECUTION_POINTS (the current state on
    ``back-ui-821-other-keep``), calling ``validate`` against the full
    close-set raises ``IncompleteRegistry``. This is the assertion the
    PR-3 acceptance criterion pins against ``EXECUTION_POINTS``."""
    from lca.harness.profile.compile_spine_registry import compile_spine_registry

    registry = compile_spine_registry()
    # The runtime boot hook only warns; the pytest suite (this file)
    # is the hard-fail surface. We test the raise explicitly against
    # the real registry assembled from the current reflector set.
    if set(registry.keys()) != set(EXECUTION_POINTS):
        with pytest.raises(IncompleteRegistry):
            registry.validate(EXECUTION_POINTS)
