"""Task 6: Verify production runtime and composer contain no legacy execution fallbacks.

This test enforces that the declarative cutover is complete:
- No legacy `_loop()` method in runtime_loop.py
- No v1 composer fallback candidates in plan_binding.py
- No legacy-authoritative dual write paths
- Non-declarative compiled plans are rejected before assembly
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_production_runtime_and_composer_contain_no_legacy_execution_fallbacks():
    """Verify that production files contain no legacy execution fallbacks."""
    paths = [
        "lca/layer2_runtime/runtime_loop.py",
        "lca/plugins/composer/plan_binding.py",
        "lca/plugins/loop_drivers/cognitive.py",
        "gateway/runs/loop_drivers.py",
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


def test_plan_binding_rejects_v1_fallback_candidates():
    """Verify that plan_binding.py does not contain v1 fallback candidates."""
    path = Path("lca/plugins/composer/plan_binding.py")
    if not path.exists():
        pytest.skip("plan_binding.py not found")
    
    source = path.read_text()
    
    # v1 fallback candidates should not exist
    assert source.count('"composer.brain"') == 0, \
        "plan_binding.py still contains v1 fallback candidate 'composer.brain'"
    assert source.count('"composer.body"') == 0, \
        "plan_binding.py still contains v1 fallback candidate 'composer.body'"
    assert source.count('"composer.perceive"') == 0, \
        "plan_binding.py still contains v1 fallback candidate 'composer.perceive'"


def test_non_declarative_compiled_plan_is_rejected_before_assembly():
    """Verify that non-declarative plans are rejected in bind_plan."""
    from unittest.mock import MagicMock
    
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.plugins.composer.plan_binding import BindPlanError, bind_plan
    
    # Create a non-declarative plan mock
    non_declarative_plan = MagicMock(spec=CompiledRunPlan)
    non_declarative_plan.is_declarative = False
    non_declarative_plan.capability_bindings = []
    non_declarative_plan.capability = MagicMock()
    non_declarative_plan.capability.provider_bindings = []
    
    # Create a mock request and scope
    request = MagicMock()
    scope = MagicMock()
    
    # bind_plan should reject non-declarative plans
    with pytest.raises(BindPlanError, match="declarative"):
        bind_plan(request, non_declarative_plan, scope=scope)


def test_dual_write_module_does_not_exist():
    """Verify that dual_write.py has been removed."""
    path = Path("lca/harness/command/dual_write.py")
    assert not path.exists(), "dual_write.py should be deleted"


def test_dual_write_tests_do_not_exist():
    """Verify that test_dual_write.py has been removed."""
    path = Path("tests/harness/test_dual_write.py")
    assert not path.exists(), "test_dual_write.py should be deleted"
