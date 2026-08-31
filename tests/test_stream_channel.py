"""Tests for LLM stream channel classification (ADR-0051 Phase 2)."""

from __future__ import annotations

import unittest

from lca.infrastructure.observability.stream.stream_channel import classify_output_channel

from lca.contracts.atoms.enums import StreamChannel


class TestStreamChannel(unittest.TestCase):
    def test_classifier_always_decision(self) -> None:
        self.assertEqual(classify_output_channel(""), StreamChannel.DECISION.value)
        self.assertEqual(
            classify_output_channel('{"action_type": "respond", "response_text": "x"}'),
            StreamChannel.DECISION.value,
        )
        self.assertEqual(
            classify_output_channel("这是用户可见的回答"),
            StreamChannel.DECISION.value,
        )


if __name__ == "__main__":
    unittest.main()
