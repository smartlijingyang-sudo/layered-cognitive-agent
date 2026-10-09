"""Test act.approve.gate with rich ApprovalRequirement contract."""

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput
from lca.contracts.protocols.graph.command import Command
from lca.contracts.runtime.trust import get_current_trust_envelope
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


@pytest.mark.asyncio
async def test_approve_gate_is_hitl_only_ignores_grant_absence() -> None:
    """ADR-0292 §10 P3 后 approve_gate 只做 HITL 路由。

    即使 ambient TrustEnvelope 没有 grant，需要审批的动作也走
    ``intervene.interrupt``；授权检查前移到 ``act.authorize``（grant_routing）。
    """
    assert get_current_trust_envelope() is None  # no envelope bound in test
    executor = ApproveGateExecutor()
    dec = Decision(
        decision_id="d-refuse-typed",
        action_type="use_tool",
        rationale="privileged shell.exec, no grant in envelope",
        confidence=1.0,
        needs_approval=True,
        tool_calls=[ToolCall(call_id="c-refuse-typed", tool_name="shell.exec", arguments={})],
    )
    req = ApprovalRequirement(
        required=True,
        reason_kind=ApprovalReasonKind.SENSITIVE_RESOURCE,
        risk_level=RiskLevel.HIGH,
        summary="shell.exec with no grant",
    )
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec, "approval_requirement": req}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.next_node == "intervene.interrupt"
    assert routing.next_hint == "approve_interrupt"
    assert result.port_values["approval_requirement"] is req


@pytest.mark.asyncio
async def test_approve_gate_present_requirement_overrides_decision_flag():
    """A present ApprovalRequirement(required=False) is authoritative: it
    overrides the model's self-reported decision.needs_approval (ADR-0292
    §10 treats that self-report as untrustworthy). §10 semantics unchanged
    from the pre-typing behavior: req.required if req is not None else
    decision.needs_approval."""
    executor = ApproveGateExecutor()
    dec = Decision(
        decision_id="d-override-typed",
        action_type="use_tool",
        rationale="",
        confidence=1.0,
        needs_approval=True,  # model asks, policy says not privileged
    )
    req = ApprovalRequirement(required=False, reason_kind=ApprovalReasonKind.NONE)
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec, "approval_requirement": req}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.next_node == "act.envelope"
    assert result.port_values["approval_requirement"] is req


@pytest.mark.asyncio
async def test_approve_gate_absent_requirement_falls_back_to_decision():
    """req=None -> the explicit None-fallback: decision.needs_approval governs."""
    executor = ApproveGateExecutor()
    dec = Decision(
        decision_id="d-fallback-typed",
        action_type="use_tool",
        rationale="",
        confidence=1.0,
        needs_approval=True,
    )
    result = await executor.node_execute(
        None,
        NodeInput(port_values={"decision": dec}),
    )
    routing = result.port_values["approval_routing"]
    assert routing.next_node == "intervene.interrupt"
