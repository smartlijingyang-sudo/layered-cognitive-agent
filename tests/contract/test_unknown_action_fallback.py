"""未知 action 降级测试 —— 使用真实 LLM 返回的 payload 做回归。

L4 韧性层：验证 FallbackActionHandler 的链式降级逻辑。
Golden Fixture 来自真实日志中 LLM "发明"的 action_type。
"""

from __future__ import annotations

import pytest

from lca.contracts.decision import StructuredDecision, ToolCall
from lca.contracts.role_team import ToolPermissionManifest
from lca.contracts.state import Budget, TypedState
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer1_cognitive.body.action_handlers import RespondHandler, UseToolHandler
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer2_runtime.fallback_handler import FALLBACK_DEGRADATION_KEY, FallbackActionHandler


def _make_state() -> TypedState:
    return TypedState(trace_id="test", task="test", budget=Budget())


def _make_registry_with_respond() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register("respond", RespondHandler())
    return registry


class TestFallbackWithResponseText:
    """策略 1：有 response_text → 降级为 respond。"""

    @pytest.mark.parametrize(
        "unknown_action",
        ["research_plan", "generate", "diagnostic_step", "structured_analysis"],
    )
    async def test_degrades_to_respond(self, unknown_action: str) -> None:
        decision = StructuredDecision(
            decision_id="dec_test",
            action_type=unknown_action,
            rationale="LLM 发明的 action",
            confidence=0.7,
            response_text="这是 LLM 生成的有效回答内容",
        )
        state = _make_state()
        registry = _make_registry_with_respond()
        fallback = FallbackActionHandler()

        observation = await fallback.handle(decision, state, registry)

        assert observation.success is True
        assert observation.payload == "这是 LLM 生成的有效回答内容"
        assert observation.extra[FALLBACK_DEGRADATION_KEY] == unknown_action

    async def test_original_action_type_preserved(self) -> None:
        decision = StructuredDecision(
            decision_id="dec_test",
            action_type="research_plan",
            rationale="test",
            confidence=0.5,
            response_text="answer",
        )
        state = _make_state()
        registry = _make_registry_with_respond()
        fallback = FallbackActionHandler()

        observation = await fallback.handle(decision, state, registry)

        assert observation.extra[FALLBACK_DEGRADATION_KEY] == "research_plan"


class TestFallbackWithToolCalls:
    """策略 2：有 tool_calls 但无 response_text → 降级为 use_tool。"""

    async def test_degrades_to_use_tool(self) -> None:
        from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool

        tool = CalculatorTool()
        tool_reg = SimpleToolRegistry()
        tool_reg.register(tool)
        safe_exec = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=["calculator"]), ConsoleObservability()
        )

        registry = ActionRegistry()
        registry.register("use_tool", UseToolHandler(tool_reg, safe_exec))

        decision = StructuredDecision(
            decision_id="dec_test",
            action_type="compute",
            rationale="LLM 发明的 action",
            confidence=0.6,
            tool_calls=[
                ToolCall(call_id="call_1", tool_name="calculator", arguments={"expression": "2+3"})
            ],
        )
        state = _make_state()
        fallback = FallbackActionHandler()

        observation = await fallback.handle(decision, state, registry)

        assert observation.success is True
        assert observation.payload == 5
        assert observation.extra[FALLBACK_DEGRADATION_KEY] == "compute"


class TestFallbackNoDegradationPath:
    """策略 3：既无 response_text 也无 tool_calls → 不可恢复失败。"""

    async def test_returns_failure(self) -> None:
        decision = StructuredDecision(
            decision_id="dec_test",
            action_type="unknown_action",
            rationale="test",
            confidence=0.3,
        )
        state = _make_state()
        registry = ActionRegistry()
        fallback = FallbackActionHandler()

        observation = await fallback.handle(decision, state, registry)

        assert observation.success is False
        assert "无法识别" in (observation.error or "")
        assert observation.extra[FALLBACK_DEGRADATION_KEY] == "unknown_action"
