"""Contract tests for ChainedDecisionGate per-gate observability (todo-28 C2).

Locks the documented semantics of ``gate_counters()`` / ``reset_gate_counters()``:
counters are keyed by gate class name, ``intercepted`` means the gate returned a
Decision ``!=`` the one it received (value semantics of the frozen dataclass),
counters are cumulative over the chain instance's lifetime, and the snapshot is
a deep copy. Add-only observability: ``enforce`` behavior itself is unchanged.
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.cognition.brain.decision_gates.chained.chained import ChainedDecisionGate
from lca.contracts.models.core.execution.decision import Decision


def _decision(action_type: str = "respond") -> Decision:
    return Decision(
        decision_id="d-1",
        action_type=action_type,
        rationale="test",
        confidence=0.9,
    )


class _PassThrough:
    """Stub gate that never rewrites the decision."""

    async def enforce(self, state, decision: Decision) -> Decision:
        return decision


class _Rewriter:
    """Stub gate that rewrites action_type; records what it received."""

    def __init__(self, action_type: str = "rewritten") -> None:
        self.action_type = action_type
        self.seen: list[Decision] = []

    async def enforce(self, state, decision: Decision) -> Decision:
        self.seen.append(decision)
        return dataclasses.replace(decision, action_type=self.action_type)


def test_fresh_chain_counters_start_zero_keyed_by_class_name() -> None:
    chain = ChainedDecisionGate(_PassThrough(), _Rewriter())
    counters = chain.gate_counters()
    assert set(counters) == {"_PassThrough", "_Rewriter"}
    assert counters["_PassThrough"] == {"evaluated": 0, "intercepted": 0}
    assert counters["_Rewriter"] == {"evaluated": 0, "intercepted": 0}


async def test_empty_chain_passes_decision_through_with_no_counters() -> None:
    chain = ChainedDecisionGate()
    decision = _decision()
    result = await chain.enforce(None, decision)
    assert result == decision
    assert chain.gate_counters() == {}


async def test_passthrough_gate_counts_evaluated_not_intercepted() -> None:
    chain = ChainedDecisionGate(_PassThrough())
    decision = _decision()
    result = await chain.enforce(None, decision)
    assert result == decision
    counters = chain.gate_counters()
    assert counters["_PassThrough"] == {"evaluated": 1, "intercepted": 0}


async def test_rewriting_gate_counts_intercepted() -> None:
    chain = ChainedDecisionGate(_Rewriter())
    result = await chain.enforce(None, _decision())
    assert result.action_type == "rewritten"
    counters = chain.gate_counters()
    assert counters["_Rewriter"] == {"evaluated": 1, "intercepted": 1}


async def test_downstream_gate_receives_upstream_rewritten_decision() -> None:
    first, second = _Rewriter("step-1"), _Rewriter("step-2")
    chain = ChainedDecisionGate(first, second)
    result = await chain.enforce(None, _decision())
    assert result.action_type == "step-2"
    assert first.seen[0].action_type == "respond"
    assert second.seen[0].action_type == "step-1"
    counters = chain.gate_counters()
    assert counters["_Rewriter"] == {"evaluated": 2, "intercepted": 2}


async def test_same_class_instances_share_one_counter_key() -> None:
    """Keying is by class name (documented); two instances accumulate into one entry."""
    chain = ChainedDecisionGate(_Rewriter("a"), _Rewriter("b"))
    result = await chain.enforce(None, _decision())
    assert result.action_type == "b"
    counters = chain.gate_counters()
    assert set(counters) == {"_Rewriter"}
    assert counters["_Rewriter"] == {"evaluated": 2, "intercepted": 2}


async def test_counters_accumulate_over_chain_lifetime() -> None:
    chain = ChainedDecisionGate(_PassThrough(), _Rewriter())
    for _ in range(3):
        await chain.enforce(None, _decision())
    counters = chain.gate_counters()
    assert counters["_PassThrough"] == {"evaluated": 3, "intercepted": 0}
    assert counters["_Rewriter"] == {"evaluated": 3, "intercepted": 3}


async def test_gate_counters_snapshot_is_a_deep_copy() -> None:
    chain = ChainedDecisionGate(_PassThrough())
    await chain.enforce(None, _decision())
    snapshot = chain.gate_counters()
    snapshot["_PassThrough"]["evaluated"] = 999
    snapshot["injected"] = {"evaluated": 1, "intercepted": 1}
    fresh = chain.gate_counters()
    assert fresh == {"_PassThrough": {"evaluated": 1, "intercepted": 0}}


async def test_reset_gate_counters_opens_fresh_window() -> None:
    chain = ChainedDecisionGate(_PassThrough(), _Rewriter())
    await chain.enforce(None, _decision())
    chain.reset_gate_counters()
    counters = chain.gate_counters()
    assert counters["_PassThrough"] == {"evaluated": 0, "intercepted": 0}
    assert counters["_Rewriter"] == {"evaluated": 0, "intercepted": 0}
    # Keys survive the reset so the new window still names every gate.
    assert set(counters) == {"_PassThrough", "_Rewriter"}
    await chain.enforce(None, _decision())
    counters = chain.gate_counters()
    assert counters["_Rewriter"] == {"evaluated": 1, "intercepted": 1}
