from __future__ import annotations

import pytest

from lca.contracts.harness.state.cost_snapshot import CostSnapshot


def test_cost_snapshot_aggregates_tokens_and_checks_budget() -> None:
    snapshot = CostSnapshot(input_tokens=100, output_tokens=50, tool_calls=2, cost_usd=0.25)

    assert snapshot.total_tokens() == 150
    assert snapshot.within(max_tokens=150, max_cost_usd=0.25) is True
    assert snapshot.within(max_tokens=149) is False


def test_cost_snapshot_rejects_negative_counters() -> None:
    with pytest.raises(ValueError):
        CostSnapshot(tool_calls=-1)
