from __future__ import annotations

import pytest

from lca.contracts.harness.tool_governance import (
    ToolGovernance,
    ToolRisk,
    governance_for,
)


def test_legacy_tool_defaults_to_read_only_governance() -> None:
    governance = governance_for(object())

    assert governance.risk is ToolRisk.READ_ONLY
    assert governance.side_effect is False


def test_side_effect_tool_requires_explicit_idempotency_policy() -> None:
    governance = ToolGovernance(
        risk=ToolRisk.INTERNAL_WRITE,
        side_effect=True,
        required_scopes=("crm.customer.write",),
        idempotency_required=True,
        compensation_tool="crm.customer.restore",
    )

    assert governance.required_scopes == ("crm.customer.write",)
    assert governance.compensation_tool == "crm.customer.restore"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"risk": ToolRisk.READ_ONLY, "side_effect": True},
        {"risk": ToolRisk.INTERNAL_WRITE, "side_effect": False, "idempotency_required": True},
        {"risk": ToolRisk.DESTRUCTIVE, "side_effect": False},
    ],
)
def test_tool_governance_rejects_inconsistent_metadata(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ToolGovernance(**kwargs)


def test_risk_policy_requires_approval_for_side_effects() -> None:
    from lca.contracts.harness.tool_governance import requires_approval

    assert requires_approval(ToolGovernance()) is False
    assert (
        requires_approval(ToolGovernance(risk=ToolRisk.EXTERNAL_SIDE_EFFECT, side_effect=True))
        is True
    )


def test_read_only_policy_is_deterministic() -> None:
    from lca.contracts.harness.tool_governance import is_read_only

    assert is_read_only(ToolGovernance()) is True
    assert is_read_only(ToolGovernance(risk=ToolRisk.INTERNAL_WRITE, side_effect=True)) is False
