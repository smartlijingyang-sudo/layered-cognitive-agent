from __future__ import annotations

import pytest

from lca.contracts.harness.capability_gate import CapabilityCheck, HermesCapabilityGate


def test_capability_gate_passes_when_all_contracts_are_implemented() -> None:
    gate = HermesCapabilityGate(
        (
            CapabilityCheck("task", True, "task projection"),
            CapabilityCheck("approval", True, "approval snapshot"),
        )
    )

    assert gate.passed is True
    gate.require_passed()


def test_capability_gate_reports_missing_capability() -> None:
    gate = HermesCapabilityGate((CapabilityCheck("replay", False, "not wired"),))

    assert gate.passed is False
    with pytest.raises(RuntimeError, match="replay"):
        gate.require_passed()
