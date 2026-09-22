"""Test ApprovalPolicyEngine, Strategy registry, and built-in strategies."""

from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.approval_engine import (
    ApprovalPolicyEngine,
    ApprovalPolicyRegistry,
    DefaultAllowStrategy,
    HITLInteractionStrategy,
    MachineAccessStrategy,
    build_default_approval_engine,
)


def test_hitl_strategy_detects_ask_user():
    strategy = HITLInteractionStrategy()
    calls = [
        ToolCall(
            call_id="c1",
            tool_name="askUserQuestion",
            arguments={"questions": ["What is your name?"]},
        )
    ]
    req = strategy.evaluate(calls, plane=None)
    assert req is not None
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.HUMAN_INTERACTION
    assert req.risk_level == RiskLevel.LOW
    assert "问答" in req.summary or "问题" in req.summary or "交互" in req.summary or "askUserQuestion" in req.summary


def test_hitl_strategy_ignores_other_tools():
    strategy = HITLInteractionStrategy()
    calls = [ToolCall(call_id="c1", tool_name="other_tool", arguments={})]
    req = strategy.evaluate(calls, plane=None)
    assert req is None


def test_machine_strategy_detects_sensitive_ssh():
    strategy = MachineAccessStrategy()
    plane = PlaneRef(
        id="p1",
        label="test",
        kind=PlaneKind.MACHINE,
        root="/home/user/workspace",
        outputs_dir="/tmp",  # noqa: S108
    )
    calls = [
        ToolCall(
            call_id="c2",
            tool_name="local_readFile",
            arguments={"path": "/home/user/.ssh/id_rsa"},
        )
    ]
    req = strategy.evaluate(calls, plane=plane)
    assert req is not None
    assert req.required is True
    assert req.reason_kind in (
        ApprovalReasonKind.SENSITIVE_RESOURCE,
        ApprovalReasonKind.UNAUTHORIZED_PATH,
    )
    assert req.target_resource == "/home/user/.ssh/id_rsa"


def test_machine_strategy_ignores_non_machine_plane():
    strategy = MachineAccessStrategy()
    plane = PlaneRef(
        id="p1",
        label="test",
        kind=PlaneKind.SANDBOX,
        root="/home/user/workspace",
        outputs_dir="/tmp",  # noqa: S108
    )
    calls = [
        ToolCall(
            call_id="c2",
            tool_name="local_readFile",
            arguments={"path": "/home/user/.ssh/id_rsa"},
        )
    ]
    req = strategy.evaluate(calls, plane=plane)
    assert req is None


def test_default_allow_strategy_always_allows():
    strategy = DefaultAllowStrategy()
    req = strategy.evaluate([], plane=None)
    assert req is not None
    assert req.required is False
    assert req.reason_kind == ApprovalReasonKind.NONE


def test_engine_evaluates_in_chain_order():
    engine = build_default_approval_engine()
    # 1. HITL tool
    calls = [ToolCall(call_id="c1", tool_name="askUserQuestion", arguments={})]
    req = engine.evaluate(calls, plane=None)
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.HUMAN_INTERACTION

    # 2. Safe tool fallback
    safe_calls = [ToolCall(call_id="c2", tool_name="safe_tool", arguments={})]
    safe_req = engine.evaluate(safe_calls, plane=None)
    assert safe_req.required is False
    assert safe_req.reason_kind == ApprovalReasonKind.NONE


def test_registry_allows_custom_strategy_injection():
    registry = ApprovalPolicyRegistry()

    class CustomHighRiskStrategy:
        strategy_name = "custom_high_risk"

        def evaluate(self, tool_calls, plane=None):
            for call in tool_calls:
                if call.tool_name == "dangerous_finance_transfer":
                    return ApprovalRequirement(
                        required=True,
                        reason_kind=ApprovalReasonKind.POLICY_RULE,
                        risk_level=RiskLevel.CRITICAL,
                        summary="高危转账拦截",
                    )
            return None

    registry.register(CustomHighRiskStrategy(), priority=0)
    engine = ApprovalPolicyEngine(strategies=registry.list_strategies())

    calls = [ToolCall(call_id="c1", tool_name="dangerous_finance_transfer", arguments={})]
    req = engine.evaluate(calls, plane=None)
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.POLICY_RULE
    assert req.risk_level == RiskLevel.CRITICAL
