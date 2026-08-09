"""Decision 意图形状归一（ADR-0045）—— 防腐层 Canonical Model。"""

from __future__ import annotations

import unittest

from lca.contracts.atoms.enums import ActionScope, ActionType
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.decision_shape import (
    hoist_response_text,
    normalize_intent_shape,
    resolve_pseudo_action,
)


def _registry():
    tool_reg = SimpleToolRegistry()
    safe_exec = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
    transport_reg = TransportRegistry()
    transport_reg.register(InternalTransport())
    return build_default_action_registry(tool_reg, safe_exec, transport_reg, scope=ActionScope.LEAD)


def _state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


class TestResolvePseudoAction(unittest.TestCase):
    def test_default_respond_aliases_without_registry(self) -> None:
        for name in ("respond", "answer", "reply", "response"):
            self.assertEqual(resolve_pseudo_action(name), ActionType.RESPOND.value)

    def test_real_tool_name_is_not_pseudo(self) -> None:
        self.assertIsNone(resolve_pseudo_action("calculator"))

    def test_registry_maps_answer_alias(self) -> None:
        reg = _registry()
        self.assertEqual(
            resolve_pseudo_action(
                "answer",
                resolve_alias=reg.normalize_alias,
                is_registered=reg.is_registered,
            ),
            ActionType.RESPOND.value,
        )


class TestNormalizeIntentShape(unittest.TestCase):
    def test_use_tool_respond_nested_response_text(self) -> None:
        raw = {
            "action_type": "use_tool",
            "tool_name": "respond",
            "arguments": {
                "response_text": "这是真正的回答",
                "rationale": "说明情况",
                "confidence": "0.95",
            },
            "rationale": "json nested",
        }
        shaped = normalize_intent_shape(raw)
        self.assertEqual(shaped["action_type"], ActionType.RESPOND.value)
        self.assertEqual(shaped["response_text"], "这是真正的回答")
        self.assertNotIn("tool_name", shaped)
        self.assertEqual(shaped["_shape_degraded_from"], "use_tool")

    def test_hoist_response_from_arguments_on_plain_respond(self) -> None:
        raw = {
            "action_type": "respond",
            "arguments": {"response_text": "袋内正文"},
        }
        shaped = normalize_intent_shape(raw)
        self.assertEqual(hoist_response_text(shaped, shaped.get("arguments", {})), "袋内正文")
        self.assertEqual(shaped["response_text"], "袋内正文")

    def test_real_use_tool_unchanged(self) -> None:
        raw = {
            "action_type": "use_tool",
            "tool_name": "calculator",
            "arguments": {"expression": "1+1"},
        }
        shaped = normalize_intent_shape(raw)
        self.assertEqual(shaped["action_type"], "use_tool")
        self.assertEqual(shaped["tool_name"], "calculator")
        self.assertNotIn("_shape_degraded_from", shaped)


class TestDecisionParserShapeIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = SimpleDecisionParser(action_registry=_registry())
        self.state = _state()

    def test_pseudo_tool_respond_becomes_canonical_respond(self) -> None:
        raw = """{
          "action_type": "use_tool",
          "tool_name": "respond",
          "arguments": {
            "response_text": "根据文件预览分析，内容不匹配。",
            "rationale": "文件是 HTML",
            "confidence": "0.95"
          },
          "rationale": "json wrap"
        }"""
        decision = self.parser.parse(raw, self.state)
        self.assertEqual(decision.action_type, ActionType.RESPOND)
        self.assertEqual(decision.response_text, "根据文件预览分析，内容不匹配。")
        self.assertEqual(decision.tool_calls, [])
        self.assertEqual(decision.degraded_from, "use_tool")
        self.assertAlmostEqual(decision.confidence, 0.95)

    def test_use_tool_calculator_still_works(self) -> None:
        raw = (
            '{"action_type": "use_tool", "tool_name": "calculator",'
            ' "arguments": {"expression": "1+1"}, "rationale": "calc", "confidence": 0.9}'
        )
        decision = self.parser.parse(raw, self.state)
        self.assertEqual(decision.action_type, ActionType.USE_TOOL)
        self.assertEqual(len(decision.tool_calls), 1)
        self.assertEqual(decision.tool_calls[0].tool_name, "calculator")
        self.assertIsNone(decision.degraded_from)

    def test_canonical_respond_unchanged(self) -> None:
        raw = (
            '{"action_type": "respond", "response_text": "你好",'
            ' "rationale": "ok", "confidence": 1.0}'
        )
        decision = self.parser.parse(raw, self.state)
        self.assertEqual(decision.action_type, ActionType.RESPOND)
        self.assertEqual(decision.response_text, "你好")
        self.assertIsNone(decision.degraded_from)


if __name__ == "__main__":
    unittest.main()
