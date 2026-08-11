"""Tests for LobeHub chat request classification."""

from __future__ import annotations

import unittest

from gateway.lobehub_bridge.request_classifier import classify_lobehub_chat_request


class TestLobeHubRequestClassifier(unittest.TestCase):
    def test_detects_title_generation_request(self) -> None:
        messages = [
            {
                "role": "system",
                "content": "You are a professional conversation summarizer.",
            },
            {
                "role": "user",
                "content": "<task>\nGenerate a concise title.\n</task>",
            },
        ]
        self.assertEqual(classify_lobehub_chat_request(messages), "title")

    def test_main_chat_request(self) -> None:
        messages = [{"role": "user", "content": "今天有什么新闻"}]
        self.assertEqual(classify_lobehub_chat_request(messages), "main")


if __name__ == "__main__":
    unittest.main()
