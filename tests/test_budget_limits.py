from __future__ import annotations

import pytest

from lca.contracts.models.core.budget import BudgetLimits


def test_budget_limits_accept_positive_runtime_ceiling() -> None:
    limits = BudgetLimits(max_steps=8, max_wall_clock_seconds=30)

    assert limits.max_steps == 8
    assert limits.max_wall_clock_seconds == 30


@pytest.mark.parametrize("max_steps,max_wall_clock_seconds", [(0, 30), (8, 0), (-1, 30)])
def test_budget_limits_reject_non_positive_ceiling(
    max_steps: int, max_wall_clock_seconds: int
) -> None:
    with pytest.raises(ValueError):
        BudgetLimits(
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )
