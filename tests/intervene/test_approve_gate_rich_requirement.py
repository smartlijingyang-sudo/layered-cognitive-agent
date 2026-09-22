"""Test act.approve.gate with rich ApprovalRequirement contract."""

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput
from lca.contracts.protocols.graph.command import Command
from lca.nodes.intervene.approve_gate import ApproveGateExecutor


@pytest.mark.asyncio
async def test_approve_gate_routes_to_interrupt_with_rich_requirement():
    executor = ApproveGateExecutor()
    dec = Decision(
        decision_id="d1",
        action_type="use_tool",
        rationale="",
        confidence=1.0,
        needs_approval=False,  # decision itself has False, but policy says True
    )
    req = ApprovalRequirement(
        required=True,
        reason_kind=ApprovalReasonKind.SENSITIVE_RESOURCE,
        risk_level=RiskLevel.HIGH,
        summary="Accessing SSH key",
        target_resource="/home/user/.ssh/id_rsa",
    )
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec, "approval_requirement": req, "command": None}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.action_type == ActionType.ASK_HUMAN
    assert routing.next_node == "intervene.interrupt"
    assert result.port_values["approval_requirement"] == req


@pytest.mark.asyncio
async def test_approve_gate_routes_to_envelope_when_requirement_not_required():
    executor = ApproveGateExecutor()
    dec = Decision(decision_id="d1", action_type="use_tool", rationale="", confidence=1.0)
    req = ApprovalRequirement(required=False, reason_kind=ApprovalReasonKind.NONE)
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec, "approval_requirement": req}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.next_node == "act.envelope"
    assert result.port_values["approval_requirement"] == req


@pytest.mark.asyncio
async def test_approve_gate_approved_command_proceeds_with_rich_requirement():
    executor = ApproveGateExecutor()
    dec = Decision(decision_id="d1", action_type="use_tool", rationale="", confidence=1.0)
    req = ApprovalRequirement(required=True, reason_kind=ApprovalReasonKind.ELEVATED_COMMAND)
    cmd = Command(kind="approve", payload=None, issued_by="user", issued_at_seq=1)
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec, "approval_requirement": req, "command": cmd}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.next_node == "act.envelope"
