from __future__ import annotations

import pytest

from lca.contracts.harness.gate.compensation import CompensationPlan


def test_compensation_plan_requires_distinct_idempotent_operation() -> None:
    plan = CompensationPlan("crm.update", "crm.restore", "comp-1")

    assert plan.can_compensate() is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation": "", "compensation_operation": "crm.restore", "idempotency_key": "c1"},
        {"operation": "crm.update", "compensation_operation": "", "idempotency_key": "c1"},
        {"operation": "crm.update", "compensation_operation": "crm.restore", "idempotency_key": ""},
    ],
)
def test_compensation_plan_rejects_incomplete_definition(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        CompensationPlan(**kwargs)
