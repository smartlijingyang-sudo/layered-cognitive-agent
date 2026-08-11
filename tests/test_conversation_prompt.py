"""Tests for prior conversation prompt formatting."""

from __future__ import annotations

import unittest

from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.state import AgentState
from lca.layer1_cognitive.brain.conversation_prompt import format_prior_conversation
from lca.layer1_cognitive.brain.reasoner import _prior_conversation_text


class TestConversationPrompt(unittest.TestCase):
    def test_format_prior_conversation_empty(self) -> None:
        self.assertEqual(format_prior_conversation(()), "(none)")

    def test_format_prior_conversation_role_lines(self) -> None:
        text = format_prior_conversation(
            (
                ConversationTurn(role="user", content="hi"),
                ConversationTurn(role="assistant", content="hello"),
            )
        )
        self.assertIn("user: hi", text)
        self.assertIn("assistant: hello", text)

    def test_prior_conversation_from_working_memory(self) -> None:
        state = AgentState(
            trace_id="t",
            task="继续",
            budget=create_budget(max_steps=5),
        )
        state.working_memory[PRIOR_CONVERSATION_WM_KEY] = [
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "收到"},
        ]
        text = _prior_conversation_text(state)
        self.assertIn("user: 第一轮", text)
        self.assertIn("assistant: 收到", text)


if __name__ == "__main__":
    unittest.main()
