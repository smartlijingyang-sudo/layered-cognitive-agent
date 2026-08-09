"""ADR-0047: tool arguments wire 防腐 —— 三态 Outcome + 执行闸门 + 不杀 loop。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.atoms.enums import ActionType, FinishReason
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_TOOL_WIRE,
    TOOL_WIRE_FINISH_REASON,
    TOOL_WIRE_INCOMPLETE,
    TOOL_WIRE_INVALID,
    TOOL_WIRE_OK,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.decision import Decision, ToolCall
from lca.contracts.models.core.llm import TokenUsage
from lca.contracts.models.core.state import AgentState, Budget
from lca.layer0_infra.llm_adapter.openai_compat._shared import (
    _RawToolCall,
    build_llm_response,
)
from lca.layer0_infra.llm_adapter.tool_arguments import (
    ToolArgumentsIncomplete,
    ToolArgumentsOk,
    normalize_finish_reason,
    resolve_tool_arguments,
)
from lca.layer1_cognitive.body.action_handlers import UseToolOperation
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser


def _state(task: str = "t") -> AgentState:
    return AgentState(trace_id="t", task=task, budget=Budget())


class TestNormalizeFinishReason(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(normalize_finish_reason("length"), FinishReason.LENGTH)
        self.assertEqual(normalize_finish_reason("max_output_tokens"), FinishReason.LENGTH)
        self.assertEqual(normalize_finish_reason("tool_calls"), FinishReason.TOOL_CALLS)
        self.assertEqual(normalize_finish_reason("stop"), FinishReason.STOP)
        self.assertEqual(normalize_finish_reason(None), FinishReason.UNKNOWN)


class TestResolveToolArguments(unittest.TestCase):
    def test_valid_object(self) -> None:
        out = resolve_tool_arguments('{"code": "print(1)", "language": "python"}')
        self.assertIsInstance(out, ToolArgumentsOk)
        assert isinstance(out, ToolArgumentsOk)
        self.assertEqual(out.arguments["code"], "print(1)")

    def test_empty_is_ok(self) -> None:
        out = resolve_tool_arguments("")
        self.assertIsInstance(out, ToolArgumentsOk)
        assert isinstance(out, ToolArgumentsOk)
        self.assertEqual(out.arguments, {})

    def test_unterminated_string_is_incomplete(self) -> None:
        """回归：Unterminated string starting at column 10 (char 9)。"""
        truncated = '{"code": "\\nimport pandas as pd\\ndf = pd.read'
        out = resolve_tool_arguments(truncated)
        self.assertIsInstance(out, ToolArgumentsIncomplete)
        assert isinstance(out, ToolArgumentsIncomplete)
        self.assertEqual(out.reason, "unterminated_or_truncated_json")

    def test_finish_reason_length_forces_incomplete_even_if_json_ok(self) -> None:
        out = resolve_tool_arguments(
            '{"code": "print(1)"}',
            finish_reason="length",
        )
        self.assertIsInstance(out, ToolArgumentsIncomplete)
        assert isinstance(out, ToolArgumentsIncomplete)
        self.assertEqual(out.reason, "finish_reason_length")


class TestBuildLlmResponseWire(unittest.TestCase):
    def test_ok_encodes_use_tool(self) -> None:
        resp = build_llm_response(
            text="",
            tool_call=_RawToolCall(
                name="run_sandbox_code",
                arguments_json='{"code": "print(1)", "language": "python"}',
                call_id="call_1",
            ),
            model="qwen-test",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="tool_calls",
        )
        payload = json.loads(resp.text)
        self.assertEqual(payload["action_type"], "use_tool")
        self.assertEqual(payload["tool_name"], "run_sandbox_code")
        self.assertEqual(payload[TOOL_WIRE_STATUS], TOOL_WIRE_OK)
        self.assertEqual(payload["arguments"]["code"], "print(1)")
        self.assertEqual(resp.finish_reason, FinishReason.TOOL_CALLS.value)

    def test_truncated_never_raises_and_stays_use_tool(self) -> None:
        truncated = '{"code": "\\nimport pandas as pd\\ndf = pd.read'
        resp = build_llm_response(
            text="thinking…",
            tool_call=_RawToolCall(
                name="run_sandbox_code",
                arguments_json=truncated,
                call_id="call_trunc",
            ),
            model="qwen3.7-plus",
            usage=None,
            finish_reason="length",
        )
        payload = json.loads(resp.text)
        # 禁止 respond 收口；禁止把半截 code 塞进 arguments
        self.assertEqual(payload["action_type"], "use_tool")
        self.assertEqual(payload["tool_name"], "run_sandbox_code")
        self.assertEqual(payload[TOOL_WIRE_STATUS], TOOL_WIRE_INCOMPLETE)
        self.assertEqual(payload["arguments"], {})
        self.assertNotEqual(payload.get("action_type"), "respond")
        self.assertEqual(resp.finish_reason, FinishReason.LENGTH.value)

    def test_does_not_silently_repair_and_execute_payload(self) -> None:
        """截断 JSON 不得被「补全」成可执行 arguments。"""
        truncated = '{"code": "print(1'
        resp = build_llm_response(
            text="",
            tool_call=_RawToolCall(
                name="run_sandbox_code",
                arguments_json=truncated,
                call_id="c",
            ),
            model="m",
            usage=None,
        )
        payload = json.loads(resp.text)
        self.assertEqual(payload[TOOL_WIRE_STATUS], TOOL_WIRE_INCOMPLETE)
        self.assertEqual(payload["arguments"], {})


class TestDecisionParserToolWire(unittest.TestCase):
    def test_incomplete_moves_to_extra_and_clears_args(self) -> None:
        raw = json.dumps(
            {
                "action_type": "use_tool",
                "tool_name": "run_sandbox_code",
                "arguments": {},
                TOOL_WIRE_STATUS: TOOL_WIRE_INCOMPLETE,
                TOOL_WIRE_REASON: "unterminated_or_truncated_json",
                TOOL_WIRE_FINISH_REASON: "length",
            }
        )
        decision = SimpleDecisionParser().parse(raw, _state())
        self.assertEqual(decision.action_type, ActionType.USE_TOOL.value)
        self.assertEqual(decision.extra[TOOL_WIRE_STATUS], TOOL_WIRE_INCOMPLETE)
        self.assertEqual(decision.tool_calls[0].arguments, {})


class TestUseToolWireGate(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_soft_fails_without_executor(self) -> None:
        registry = MagicMock()
        executor = AsyncMock()
        op = UseToolOperation(registry, executor)
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL.value,
            rationale="wire incomplete",
            confidence=0.5,
            tool_calls=[
                ToolCall(
                    call_id="call_x",
                    tool_name="run_sandbox_code",
                    arguments={},
                )
            ],
            extra={
                TOOL_WIRE_STATUS: TOOL_WIRE_INCOMPLETE,
                TOOL_WIRE_REASON: "finish_reason_length",
                TOOL_WIRE_FINISH_REASON: "length",
            },
        )
        obs = await op.execute(decision, _state())
        self.assertFalse(obs.success)
        self.assertIsNotNone(obs.error)
        assert obs.error is not None
        self.assertIn("tool_wire_incomplete", obs.error)
        self.assertEqual(obs.extra[FAILURE_KIND], FAILURE_KIND_TOOL_WIRE)
        executor.execute.assert_not_called()
        registry.get.assert_not_called()

    async def test_ok_status_still_executes(self) -> None:
        tool = MagicMock()
        tool.name = "calculator"
        registry = MagicMock()
        registry.get.return_value = tool
        executor = AsyncMock()
        from lca.contracts.models.core.decision import Observation

        executor.execute.return_value = Observation(
            observation_id="obs_1",
            success=True,
            payload={"ok": True},
        )
        op = UseToolOperation(registry, executor)
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL.value,
            rationale="",
            confidence=0.9,
            tool_calls=[
                ToolCall(call_id="c1", tool_name="calculator", arguments={"expression": "1+1"})
            ],
            extra={TOOL_WIRE_STATUS: TOOL_WIRE_OK},
        )
        obs = await op.execute(decision, _state())
        self.assertTrue(obs.success)
        executor.execute.assert_awaited_once()


class TestEndToEndWireThroughParserAndBody(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_adapter_payload_soft_fails_in_body(self) -> None:
        resp = build_llm_response(
            text="",
            tool_call=_RawToolCall(
                name="run_sandbox_code",
                arguments_json='{"code": "import pandas',
                call_id="call_e2e",
            ),
            model="m",
            usage=None,
            finish_reason="length",
        )
        decision = SimpleDecisionParser().parse(resp.text, _state("analyze"))
        self.assertEqual(decision.extra[TOOL_WIRE_STATUS], TOOL_WIRE_INCOMPLETE)

        registry = MagicMock()
        executor = AsyncMock()
        obs = await UseToolOperation(registry, executor).execute(decision, _state("analyze"))
        self.assertFalse(obs.success)
        executor.execute.assert_not_called()
        # 不得伪装成 invalid 以外的收口
        self.assertNotEqual(decision.action_type, ActionType.RESPOND.value)
        self.assertIn(decision.extra[TOOL_WIRE_STATUS], (TOOL_WIRE_INCOMPLETE, TOOL_WIRE_INVALID))


if __name__ == "__main__":
    unittest.main()
