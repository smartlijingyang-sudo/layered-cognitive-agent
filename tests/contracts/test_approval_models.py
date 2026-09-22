"""Test ApprovalRequirement domain model and ApprovalStrategy protocol contracts."""

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)


def test_approval_requirement_defaults():
    req = ApprovalRequirement()
    assert req.required is False
    assert req.reason_kind == ApprovalReasonKind.NONE
    assert req.risk_level == RiskLevel.LOW
    assert req.summary == ""
    assert req.target_resource is None
    assert req.details == {}


def test_approval_requirement_frozen():
    req = ApprovalRequirement(required=True, reason_kind=ApprovalReasonKind.HUMAN_INTERACTION)
    with pytest.raises(FrozenInstanceError):
        req.required = False  # type: ignore[misc]


def test_approval_reason_kind_values():
    assert ApprovalReasonKind.NONE.value == "none"
    assert ApprovalReasonKind.HUMAN_INTERACTION.value == "human_interaction"
    assert ApprovalReasonKind.SENSITIVE_RESOURCE.value == "sensitive_resource"
    assert ApprovalReasonKind.UNAUTHORIZED_PATH.value == "unauthorized_path"
    assert ApprovalReasonKind.ELEVATED_COMMAND.value == "elevated_command"
    assert ApprovalReasonKind.POLICY_RULE.value == "policy_rule"


def test_risk_level_values():
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.CRITICAL.value == "critical"
