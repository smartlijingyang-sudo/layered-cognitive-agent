from __future__ import annotations

import pytest

from lca.contracts.harness.context_budget import ContextBudgeter
from lca.contracts.models.core.perception import ContextItem


def test_context_budgeter_preserves_input_order_within_budget() -> None:
    items = (
        ContextItem("memory", "one", "test"),
        ContextItem("memory", "two", "test"),
        ContextItem("memory", "three", "test"),
    )

    result = ContextBudgeter(7).trim(items)

    assert [item.payload for item in result] == ["one", "two"]


def test_context_budgeter_rejects_non_positive_budget() -> None:
    with pytest.raises(ValueError):
        ContextBudgeter(0)
