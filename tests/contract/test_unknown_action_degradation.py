"""未知 action 优雅降级测试 —— 使用真实 LLM 返回的 payload 做回归。

防腐层契约：GracefulDegradation 把越界决策改写为词表内等价行动，
降级溯源沿 Decision → Observation 端到端传播。
Golden Fixture 来自真实日志中 LLM "发明"的 action_type。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision, Observation, ToolCall
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer1_cognitive.body.action_handlers import RespondOperation, UseToolOperation
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.degradation import GracefulDegradation


def _make_state() -> AgentState:
    return AgentState(trace_id="test", task="test", budget=Budget())


def _respond_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(ActionType.RESPOND, RespondOperation())
    return registry


def _tool_registry_with_calculator() -> ActionRegistry:
    tool_registry = SimpleToolRegistry()
    tool_registry.register(CalculatorTool())
    safe_executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=["calculator"]))
    registry = ActionRegistry()
    registry.register(ActionType.USE_TOOL, UseToolOperation(tool_registry, safe_executor))
    return registry


class _NeverExecutedAction:
    """仅用于占位注册 use_tool 词表项，任何执行都意味着优先级断言失效。"""

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        raise AssertionError("respond 应优先于 use_tool，本占位 Action 不应被执行")


def _decision(
    action_type: str,
    response_text: str | None = None,
    tool_calls: list[ToolCall] | None = None,
) -> Decision:
    return Decision(
        decision_id="dec_test",
        action_type=action_type,
        rationale="LLM 发明的 action",
        confidence=0.6,
        response_text=response_text,
        tool_calls=tool_calls or [],
    )


class TestGracefulDegradation:
    """策略单测：按内容优先级改写越界 action_type。"""

    @pytest.mark.parametrize(
        "unknown_action",
        ["research_plan", "generate", "diagnostic_step", "structured_analysis"],
    )
    def test_degrades_to_respond_when_response_text_present(self, unknown_action: str) -> None:
        decision = _decision(unknown_action, response_text="这是 LLM 生成的有效回答内容")
        degraded = GracefulDegradation().degrade(decision, _respond_registry())
        assert degraded.action_type == ActionType.RESPOND
        assert degraded.degraded_from == unknown_action
        assert degraded.response_text == "这是 LLM 生成的有效回答内容"

    def test_degrades_to_use_tool_when_tool_calls_present(self) -> None:
        calls = [
            ToolCall(call_id="call_1", tool_name="calculator", arguments={"expression": "2+3"})
        ]
        decision = _decision("compute", tool_calls=calls)
        degraded = GracefulDegradation().degrade(decision, _tool_registry_with_calculator())
        assert degraded.action_type == ActionType.USE_TOOL
        assert degraded.degraded_from == "compute"
        assert degraded.tool_calls == calls

    def test_prefers_respond_over_use_tool(self) -> None:
        calls = [ToolCall(call_id="call_1", tool_name="calculator", arguments={})]
        decision = _decision("multi_content", response_text="answer", tool_calls=calls)
        registry = _respond_registry()
        registry.register(ActionType.USE_TOOL, _NeverExecutedAction())
        degraded = GracefulDegradation().degrade(decision, registry)
        assert degraded.action_type == ActionType.RESPOND

    def test_returns_unchanged_without_degradable_content(self) -> None:
        decision = _decision("unknown_action")
        degraded = GracefulDegradation().degrade(decision, _respond_registry())
        assert degraded.action_type == "unknown_action"
        assert degraded.degraded_from is None

    def test_returns_unchanged_when_targets_unregistered(self) -> None:
        decision = _decision("research_plan", response_text="answer")
        degraded = GracefulDegradation().degrade(decision, ActionRegistry())
        assert degraded.action_type == "research_plan"
        assert degraded.degraded_from is None


class TestParserNormalizesUnknownAction:
    """防腐层集成：LLM 原始输出解析后即落在词表内。"""

    def test_invented_action_with_text_parses_to_respond(self) -> None:
        parser = SimpleDecisionParser(action_registry=_respond_registry())
        raw = (
            '{"action_type": "research_plan", "response_text": "结论内容",'
            ' "rationale": "llm invented", "confidence": 0.7}'
        )
        decision = parser.parse(raw, _make_state())
        assert decision.action_type == ActionType.RESPOND
        assert decision.degraded_from == "research_plan"

    def test_alias_resolution_is_not_degradation(self) -> None:
        registry = _respond_registry()
        registry.register_alias("answer", ActionType.RESPOND)
        parser = SimpleDecisionParser(action_registry=registry)
        raw = '{"action_type": "answer", "response_text": "ok", "confidence": 0.9}'
        decision = parser.parse(raw, _make_state())
        assert decision.action_type == ActionType.RESPOND
        assert decision.degraded_from is None


class TestDegradationEndToEnd:
    """Decision → SimpleBody → Observation：降级溯源端到端传播。"""

    async def test_respond_degradation_propagates_to_observation(self) -> None:
        registry = _respond_registry()
        parser = SimpleDecisionParser(action_registry=registry)
        raw = (
            '{"action_type": "structured_analysis", "response_text": "有效回答", "confidence": 0.7}'
        )
        decision = parser.parse(raw, _make_state())

        observation = await SimpleBody(action_registry=registry).act(decision, _make_state())

        assert observation.success is True
        assert observation.payload == "有效回答"
        assert observation.degraded_from == "structured_analysis"
        assert observation.extra[OBS_DEGRADED_FROM] == "structured_analysis"

    async def test_use_tool_degradation_executes_and_propagates(self) -> None:
        registry = _tool_registry_with_calculator()
        parser = SimpleDecisionParser(action_registry=registry)
        raw = (
            '{"action_type": "compute", "tool_name": "calculator",'
            ' "arguments": {"expression": "2+3"}, "confidence": 0.6}'
        )
        decision = parser.parse(raw, _make_state())

        observation = await SimpleBody(action_registry=registry).act(decision, _make_state())

        assert observation.success is True
        assert observation.payload == 5
        assert observation.degraded_from == "compute"

    async def test_unrecoverable_action_is_rejected_by_body(self) -> None:
        registry = _respond_registry()
        parser = SimpleDecisionParser(action_registry=registry)
        raw = '{"action_type": "unknown_action", "confidence": 0.3}'
        decision = parser.parse(raw, _make_state())
        assert decision.action_type == "unknown_action"

        with pytest.raises(UnregisteredActionError) as ei:
            await SimpleBody(action_registry=registry).act(decision, _make_state())
        assert ei.value.action_type == "unknown_action"
