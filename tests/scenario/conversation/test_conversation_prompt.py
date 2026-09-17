"""Tests for prior conversation prompt formatting."""

from __future__ import annotations

import unittest

from lca.cognition.brain.prompt.conversation_prompt import format_prior_conversation
from lca.contracts.models.core.conversation.conversation import ConversationTurn


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


if __name__ == "__main__":
    unittest.main()
