"""Housekeeper uses LLM_OPENAI_BASE_URL; agent Anthropic URL stays off that client."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from lca.layer0_infra.llm_resolver import (
    LLMUnavailableError,
    get_async_openai_client,
    llm_openai_credentials,
    reset_async_openai_client,
)


class TestHousekeeperEndpoint(unittest.TestCase):
    def tearDown(self) -> None:
        reset_async_openai_client()

    def test_openai_url_wins_over_anthropic_agent_url(self) -> None:
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
            "LLM_MODEL": "qwen3.7-plus",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            key, base, model = llm_openai_credentials()
        self.assertEqual(key, "sk-test")
        self.assertEqual(base, "https://coding.dashscope.aliyuncs.com/v1")
        self.assertEqual(model, "qwen3.7-plus")

    def test_anthropic_agent_url_is_not_a_housekeeper_fallback(self) -> None:
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "LLM_MODEL": "qwen3.7-plus",
        }
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "LLM_MODEL": "qwen3.7-plus",
            "LLM_OPENAI_BASE_URL": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            _key, base, _model = llm_openai_credentials()
        self.assertIsNone(base)

    def test_openai_agent_url_still_serves_housekeeper(self) -> None:
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "LLM_MODEL": "qwen-plus",
            "LLM_OPENAI_BASE_URL": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            _key, base, _model = llm_openai_credentials()
        self.assertEqual(base, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_client_refuses_missing_openai_url(self) -> None:
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "LLM_OPENAI_BASE_URL": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            reset_async_openai_client()
            with self.assertRaises(LLMUnavailableError) as ctx:
                get_async_openai_client()
        self.assertIn("LLM_OPENAI_BASE_URL", str(ctx.exception))

    def test_client_uses_openai_url(self) -> None:
        env = {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
        }
        created: list[tuple[str | None, str | None]] = []

        class _FakeClient:
            def __init__(self, *, api_key: str | None, base_url: str | None) -> None:
                created.append((api_key, base_url))

        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch("openai.AsyncOpenAI", _FakeClient),
        ):
            reset_async_openai_client()
            client = get_async_openai_client()
        self.assertEqual(created, [("sk-test", "https://coding.dashscope.aliyuncs.com/v1")])
        self.assertIsInstance(client, _FakeClient)
