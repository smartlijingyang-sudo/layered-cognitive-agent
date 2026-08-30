"""Tool turns stay on the provider wire, not as CONTEXT prose."""

from __future__ import annotations

import unittest

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.llm_adapter.openai_compat._history import (
    anthropic_messages_with_history,
    openai_messages_with_history,
)
from lca.cognition.brain.reasoner import _context_lines
from lca.cognition.brain.tool_conversation import build_tool_history


def _tool_turn() -> Turn:
    return Turn(
        decision=Decision(
            decision_id="dec1",
            action_type="use_tool",
            rationale="",
            confidence=1.0,
            tool_calls=[
                ToolCall(
                    call_id="toolu_1",
                    tool_name="read_file",
                    arguments={"path": "/mnt/data/a.html"},
                )
            ],
        ),
        observation=Observation(
            observation_id="obs1",
            success=True,
            payload={"summary": "<html>ok</html>"},
        ),
    )


class TestToolConversation(unittest.TestCase):
    def test_skill_history_is_markdown_not_json_wrapper(self) -> None:
        state = AgentState(trace_id="t", task="pptx", budget=Budget(), step=1)
        state.history.append(
            Turn(
                decision=Decision(
                    decision_id="dec1",
                    action_type="use_tool",
                    rationale="",
                    confidence=1.0,
                    tool_calls=[
                        ToolCall(
                            call_id="toolu_skill",
                            tool_name="activate_skill",
                            arguments={"skill_id": "officecli"},
                        )
                    ],
                ),
                observation=Observation(
                    observation_id="obs1",
                    success=True,
                    payload={
                        "text": "# officecli\n\n通过 run_command 调用。",
                        "skill_id": "officecli",
                        "state": {"content": "# officecli\n\n通过 run_command 调用。"},
                    },
                ),
            )
        )
        history = build_tool_history(state)
        self.assertEqual(history[1]["content"], "# officecli\n\n通过 run_command 调用。")
        self.assertNotIn("skill_id", history[1]["content"])

    def test_history_is_assistant_then_tool(self) -> None:
        state = AgentState(trace_id="t", task="pdf", budget=Budget(), step=1)
        state.history.append(_tool_turn())
        history = build_tool_history(state)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "assistant")
        self.assertEqual(history[0]["tool_calls"][0]["id"], "toolu_1")
        self.assertEqual(history[0]["tool_calls"][0]["name"], "read_file")
        self.assertEqual(history[1]["role"], "tool")
        self.assertEqual(history[1]["tool_call_id"], "toolu_1")
        self.assertIn("<html>ok</html>", history[1]["content"])

    def test_context_has_no_execution_trace(self) -> None:
        state = AgentState(trace_id="t", task="pdf", budget=Budget(), step=1)
        state.history.append(_tool_turn())
        text = _context_lines(state)
        self.assertEqual(text, "(无历史上下文)")
        self.assertNotIn("use_tool", text)
        self.assertNotIn("read_file", text)

    def test_context_does_not_reprint_working_memory_tool_payload(self) -> None:
        state = AgentState(trace_id="t", task="pptx", budget=Budget(), step=1)
        state.history.append(_tool_turn())
        state.retrieved_context = [
            MemoryRecord(
                record_id="m1",
                content="TOOL_RESULT: {'text': '# officecli', 'skill_id': 'officecli'}",
                memory_type=MemoryLayer.WORKING,
                importance=0.9,
                kind=MemoryRecordKind.TOOL_RESULT,
            )
        ]
        text = _context_lines(state)
        self.assertNotIn("TOOL_RESULT", text)
        self.assertNotIn("officecli", text)
        self.assertNotIn("skill_id", text)

    def test_anthropic_history_is_tool_use_then_tool_result(self) -> None:
        state = AgentState(trace_id="t", task="pdf", budget=Budget(), step=1)
        state.history.append(_tool_turn())
        messages = anthropic_messages_with_history("USER_TASK", build_tool_history(state))
        self.assertEqual(messages[0], {"role": "user", "content": "USER_TASK"})
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[1]["content"][0]["id"], "toolu_1")
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")
        self.assertEqual(messages[2]["content"][0]["tool_use_id"], "toolu_1")

    def test_openai_history_is_tool_calls_then_tool_role(self) -> None:
        state = AgentState(trace_id="t", task="pdf", budget=Budget(), step=1)
        state.history.append(_tool_turn())
        messages = openai_messages_with_history("USER_TASK", build_tool_history(state))
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "read_file")
        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "toolu_1")
