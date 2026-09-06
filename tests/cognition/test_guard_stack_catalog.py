"""Guard stack catalog tests (ADR-0197)."""

from __future__ import annotations

from lca.contracts.models.core.policy.guard_stack import GUARD_STACK_CATALOG


def test_catalog_covers_think_and_act_planes() -> None:
    planes = {entry.plane for entry in GUARD_STACK_CATALOG}
    assert "think" in planes
    assert "act" in planes
    assert "stop" in planes


def test_delivery_gate_is_semantic_tier() -> None:
    delivery = next(entry for entry in GUARD_STACK_CATALOG if entry.id == "gate.delivery-satisfied")
    assert delivery.tier == "semantic"
    assert delivery.plane == "think"
