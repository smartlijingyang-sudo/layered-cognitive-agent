from __future__ import annotations

from pathlib import Path


def test_runtime_source_contains_no_legacy_loop_or_policy_engine() -> None:
    source = Path("lca/layer2_runtime/runtime_loop.py").read_text(encoding="utf-8")

    assert "def _loop(" not in source
    assert "DefaultControlPolicyEngine" not in source
    assert "return await self._loop" not in source


def test_legacy_control_policy_engine_has_been_replaced_by_contributions() -> None:
    assert not Path("lca/layer2_runtime/control_policies.py").exists()
    assert not Path("tests/layer2_runtime/test_control_policies.py").exists()
    assert not Path("tests/layer2_runtime/test_control_runtime_execution.py").exists()


def test_runtime_construction_has_no_legacy_control_or_topology_dependencies() -> None:
    runtime_source = Path("lca/layer2_runtime/runtime_loop.py").read_text(encoding="utf-8")
    factory_source = Path("lca/plugins/composer/runtime_factory.py").read_text(encoding="utf-8")

    assert "control_plan" not in runtime_source
    assert "topology" not in runtime_source
    assert "control_plan" not in factory_source
    assert "topology" not in factory_source


def test_plan_binding_has_no_v1_composer_fallback() -> None:
    source = Path("lca/plugins/composer/plan_binding.py").read_text(encoding="utf-8")

    assert "Read-only v1 compatibility" not in source
    assert 'composer.brain", "composer.body", "composer.perceive' not in source
    assert "plan binding requires a declarative CompiledRunPlan" in source
