"""Regression tests for the v2 plan compiler (``lca_kernel.plan.plan_compile``).

Covers the contract surface that ``lca-ops kernel_compose --json`` exposes
to operators and agents: ``CompiledRunPlan.plugin_specs`` must reflect
the resolved profile so callers can enumerate the active plugin catalog
without re-running ``resolve_profile``.
"""

from __future__ import annotations

from pathlib import Path

from lca.harness.profile.resolve.resolve import resolve_profile
from lca_kernel.plan.plan_compile import compile_plan

PROFILE = Path("profiles/web-standard.yaml")


def test_plugin_specs_carries_every_enabled_plugin() -> None:
    """ADR-0221 P3 fix: ``plugin_specs`` must enumerate the resolved plugin set.

    Prior to the fix, ``plan_compile.compile_plan`` left ``plugin_specs=()``
    with a comment promising the projection would "live in plugin_id index,
    not here". The promised index was never built, so the only CLI surface
    (``lca-ops kernel_compose --json``) reported ``plugin_specs=[]`` and
    ``plugin_count=0``, making it impossible to enumerate loaded plugins
    from the compiled plan alone. The fix restores the projection here.
    """
    resolved = resolve_profile(PROFILE)
    plan = compile_plan(resolved)

    spec_ids = {spec.id for spec in plan.plugin_specs}
    enabled_ids = {p.id for p in resolved.plugins if not p.disabled}

    assert enabled_ids <= spec_ids, (
        f"missing in plugin_specs: {enabled_ids - spec_ids}; "
        f"unexpected extras: {spec_ids - enabled_ids}"
    )
    assert len(plan.plugin_specs) == len(enabled_ids)


def test_plugin_specs_preserves_layer_and_module() -> None:
    """Operators must be able to filter by ``layer`` and read ``implementation.module``.

    These two fields are the minimum a CLI / dashboard needs to render the
    loaded-plugin tree without re-running ``resolve_profile``.
    """
    resolved = resolve_profile(PROFILE)
    plan = compile_plan(resolved)

    layers = {spec.layer for spec in plan.plugin_specs}
    assert layers <= {"L0", "L1", "L2", "L3", "L4"}
    assert "L0" in layers and "L1" in layers, "layer coverage regressed"

    sample = next(spec for spec in plan.plugin_specs if spec.implementation.module)
    assert sample.implementation.module.startswith("lca.plugins.")
