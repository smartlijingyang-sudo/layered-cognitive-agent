"""Boot-time observability compile gate (ADR-0198 P2)."""

from __future__ import annotations

from lca.harness.composition.observability_compile import compile_observability_boot_plan


def test_boot_observability_plan_compiles() -> None:
    plan = compile_observability_boot_plan()
    assert plan.ok
    assert plan.closure_events
    assert "journal.step_tree" in plan.bindings_by_projection
