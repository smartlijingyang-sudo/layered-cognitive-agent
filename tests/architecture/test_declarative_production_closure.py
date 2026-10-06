"""Task 6: Verify production runtime and composer contain no legacy execution fallbacks.

This test enforces that the declarative cutover is complete:
- No legacy `_loop()` method in runtime_loop.py
- No v1 composer fallback candidates in plan_binding.py
- No legacy-authoritative dual write paths
- Non-declarative compiled plans are rejected before assembly
"""

from __future__ import annotations

# Scripted/mock run: boots the kernel, so it must pass the reasoner
# fail-loud credential gate (see tests/conftest.py _ensure_no_env).
# The mock/scripted adapter never touches the network; ambient dummy key is enough.
__keep_llm_key__ = True


from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_production_runtime_and_composer_contain_no_legacy_execution_fallbacks():
    """Verify that production files contain no legacy execution fallbacks."""
    paths = [
        "lca/runtime/runtime_loop.py",
        "lca/plugins/composer/composition/plan_binding.py",
        "lca/plugins/loop_drivers/cognitive.py",
        "lca/plugins/transport/webserver/carrier/runs/execute/loop_drivers.py",
    ]
    forbidden = (
        "def _loop(",
        "return await self._loop",
        "DualWriteExecutor",
    )

    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            continue
        source = path.read_text()
        violations = [token for token in forbidden if token in source]
        assert not violations, f"{path_str} contains legacy tokens: {violations}"


def test_production_assembly_requires_profile_selected_phase_observer() -> None:
    """Phase observation must be an explicit production capability binding."""

    runtime_assembly = Path("lca/plugins/composer/runtime/runtime/assembly.py").read_text()
    runtime_capabilities = Path("lca/plugins/composer/runtime/runtime/capabilities.py").read_text()
    runtime_binding = Path("lca/plugins/composer/runtime/runtime/binding.py").read_text()

    assert "resolve_runtime_capabilities" in runtime_assembly
    assert "bind_runtime_graph(" in runtime_assembly
    assert "ProductionRuntimeDeps" not in runtime_assembly
    assert "PHASE_OBSERVER" in runtime_capabilities
    assert "require_declared_capabilities(" in runtime_capabilities
    assert "phase_observer=capabilities.phase_observer" in runtime_binding
    # The legacy lca/loop/transaction.py (PhaseExecutionTransaction) is fully
    # retired; phase observation lives only in the capability binding above.
    assert not Path("lca/loop/transaction.py").exists()


def test_plan_binding_rejects_v1_fallback_candidates():
    """Verify that plan_binding.py does not contain v1 fallback candidates."""
    path = Path("lca/plugins/composer/composition/plan_binding.py")
    if not path.exists():
        pytest.skip("plan_binding.py not found")

    source = path.read_text()

    # v1 fallback candidates should not exist
    assert source.count('"composer.brain"') == 0, (
        "plan_binding.py still contains v1 fallback candidate 'composer.brain'"
    )
    assert source.count('"composer.body"') == 0, (
        "plan_binding.py still contains v1 fallback candidate 'composer.body'"
    )
    assert source.count('"composer.perceive"') == 0, (
        "plan_binding.py still contains v1 fallback candidate 'composer.perceive'"
    )


async def test_incomplete_runnable_profile_is_rejected_during_boot_before_binding():
    """Plan validation belongs to boot, before a composer can consume a scope."""
    from lca.harness.profile.resolve.resolve import resolve_profile
    from lca_kernel import run_resolved_kernel

    resolved = resolve_profile("profiles/web-standard.yaml")
    missing_stop = tuple(
        plugin for plugin in resolved.plugins if plugin.id != "phase.stop.standard"
    )
    incomplete = replace(resolved, plugins=missing_stop)

    with pytest.raises(
        ValueError,
        match=r"PG-001: declared phase node .*phase\.stop\.standard.*active 'stop' phase executor",
    ):
        await run_resolved_kernel(incomplete)


def test_plan_binding_rejects_a_scope_without_the_boot_frozen_plan():
    """Composition must not silently create a second plan from profile data."""
    from lca.contracts.mechanisms.capability.capability import MissingCapabilityError
    from lca.harness.profile.resolve.resolve import resolve_profile
    from lca.plugins.composer.composition.plan_binding import compiled_plan_from_scope

    resolved = resolve_profile("profiles/web-standard.yaml")

    with pytest.raises(MissingCapabilityError, match="compiled_run_plan"):
        compiled_plan_from_scope(SimpleNamespace(resolved_profile=resolved))


def test_dual_write_module_does_not_exist():
    """Verify that dual_write.py has been removed."""
    path = Path("lca/harness/command/dual_write.py")
    assert not path.exists(), "dual_write.py should be deleted"


def test_dual_write_tests_do_not_exist():
    """Verify that test_dual_write.py has been removed."""
    path = Path("tests/harness/test_dual_write.py")
    assert not path.exists(), "test_dual_write.py should be deleted"
