"""LLMSettings / build_generation_kwargs — Qwen/百炼参数与 parallel_tool_calls。"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from lca.infrastructure.llm_adapter.settings import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TOKENS_WITH_TOOLS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    LLMSettings,
    build_generation_kwargs,
    clear_llm_settings_cache,
    is_qwen_model,
)


class TestIsQwenModel(unittest.TestCase):
    def test_prefix(self) -> None:
        self.assertTrue(is_qwen_model("qwen3.7-plus"))
        self.assertTrue(is_qwen_model("Qwen-Plus"))
        self.assertFalse(is_qwen_model("gpt-4.1"))


class TestBuildGenerationKwargs(unittest.TestCase):
    def setUp(self) -> None:
        clear_llm_settings_cache()

    def tearDown(self) -> None:
        clear_llm_settings_cache()

    def test_qwen_has_tools_enables_thinking_by_default(self) -> None:
        settings = LLMSettings(enable_thinking=None, enable_search=None, top_k=None)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=True,
            call_kwargs={},
            settings=settings,
        )
        self.assertTrue(out["extra_body"]["enable_thinking"])

    def test_qwen_defaults_enable_thinking_and_sampling(self) -> None:
        settings = LLMSettings(enable_thinking=None, enable_search=None, top_k=None)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=False,
            call_kwargs={},
            settings=settings,
        )
        self.assertEqual(out["temperature"], DEFAULT_TEMPERATURE)
        self.assertEqual(out["top_p"], DEFAULT_TOP_P)
        self.assertEqual(out["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertNotIn("parallel_tool_calls", out)
        extra = out["extra_body"]
        self.assertTrue(extra["enable_thinking"])
        self.assertEqual(extra["top_k"], DEFAULT_TOP_K)
        self.assertNotIn("enable_search", extra)

    def test_has_tools_raises_default_max_tokens(self) -> None:
        settings = LLMSettings(max_tokens=DEFAULT_MAX_TOKENS)
        out = build_generation_kwargs(
            model="gpt-4.1",
            has_tools=True,
            call_kwargs={},
            settings=settings,
        )
        self.assertEqual(out["max_tokens"], DEFAULT_MAX_TOKENS_WITH_TOOLS)
        self.assertTrue(out["parallel_tool_calls"])

    def test_explicit_max_tokens_overrides_tools_default(self) -> None:
        settings = LLMSettings(max_tokens=DEFAULT_MAX_TOKENS)
        out = build_generation_kwargs(
            model="gpt-4.1",
            has_tools=True,
            call_kwargs={"max_tokens": 2048},
            settings=settings,
        )
        self.assertEqual(out["max_tokens"], 2048)

    def test_non_qwen_skips_qwen_extra_body_defaults(self) -> None:
        settings = LLMSettings(enable_thinking=None, enable_search=None, top_k=None)
        out = build_generation_kwargs(
            model="gpt-4.1",
            has_tools=False,
            call_kwargs={},
            settings=settings,
        )
        self.assertNotIn("extra_body", out)

    def test_parallel_tool_calls_only_when_tools(self) -> None:
        settings = LLMSettings(parallel_tool_calls=True, enable_thinking=False)
        with_tools = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=True,
            call_kwargs={},
            settings=settings,
        )
        without = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=False,
            call_kwargs={},
            settings=settings,
        )
        self.assertTrue(with_tools["parallel_tool_calls"])
        self.assertNotIn("parallel_tool_calls", without)

    def test_parallel_tool_calls_false_honored(self) -> None:
        settings = LLMSettings(parallel_tool_calls=True, enable_thinking=False)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=True,
            call_kwargs={"parallel_tool_calls": False},
            settings=settings,
        )
        self.assertFalse(out["parallel_tool_calls"])

    def test_enable_search_with_search_options(self) -> None:
        settings = LLMSettings(
            enable_thinking=False,
            enable_search=True,
            search_strategy="max",
            forced_search=True,
            enable_source=True,
            enable_citation=True,
            citation_format="[ref_<number>]",
            search_top_k=10,
            freshness="30",
            top_k=None,
        )
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=False,
            call_kwargs={},
            settings=settings,
        )
        extra = out["extra_body"]
        self.assertTrue(extra["enable_search"])
        self.assertEqual(
            extra["search_options"],
            {
                "search_strategy": "max",
                "forced_search": True,
                "enable_source": True,
                "enable_citation": True,
                "citation_format": "[ref_<number>]",
                "search_top_k": 10,
                "freshness": "30",
            },
        )

    def test_caller_extra_body_wins(self) -> None:
        settings = LLMSettings(enable_thinking=True, top_k=20)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=False,
            call_kwargs={"extra_body": {"enable_thinking": False, "foo": 1}},
            settings=settings,
        )
        self.assertFalse(out["extra_body"]["enable_thinking"])
        self.assertEqual(out["extra_body"]["foo"], 1)
        self.assertEqual(out["extra_body"]["top_k"], 20)

    def test_call_kwargs_override_settings(self) -> None:
        settings = LLMSettings(temperature=0.6, max_tokens=4096, enable_thinking=True)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=False,
            call_kwargs={"temperature": 0.2, "max_tokens": 512, "enable_thinking": False},
            settings=settings,
        )
        self.assertEqual(out["temperature"], 0.2)
        self.assertEqual(out["max_tokens"], 512)
        self.assertFalse(out["extra_body"]["enable_thinking"])

    def test_repetition_penalty_in_extra_body(self) -> None:
        settings = LLMSettings(
            enable_thinking=False,
            repetition_penalty=1.1,
            top_k=None,
        )
        out = build_generation_kwargs(
            model="qwen-plus",
            has_tools=False,
            call_kwargs={},
            settings=settings,
        )
        self.assertEqual(out["extra_body"]["repetition_penalty"], 1.1)

    def test_qwen_has_tools_keeps_env_enable_thinking_true(self) -> None:
        settings = LLMSettings(enable_thinking=True)
        out = build_generation_kwargs(
            model="qwen3.7-plus",
            has_tools=True,
            call_kwargs={},
            settings=settings,
        )
        self.assertTrue(out["extra_body"]["enable_thinking"])

    def test_env_overrides_settings(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "LLM_TEMPERATURE": "0.3",
                "LLM_PARALLEL_TOOL_CALLS": "false",
                "LLM_ENABLE_THINKING": "false",
                "LLM_MAX_TOKENS": "1024",
            },
            clear=False,
        ):
            clear_llm_settings_cache()
            settings = LLMSettings()
            self.assertEqual(settings.temperature, 0.3)
            self.assertFalse(settings.parallel_tool_calls)
            self.assertFalse(settings.enable_thinking)
            self.assertEqual(settings.max_tokens, 1024)
            out = build_generation_kwargs(
                model="qwen3.7-plus",
                has_tools=True,
                call_kwargs={},
                settings=settings,
            )
            self.assertEqual(out["temperature"], 0.3)
            self.assertFalse(out["parallel_tool_calls"])
            self.assertFalse(out["extra_body"]["enable_thinking"])


if __name__ == "__main__":
    unittest.main()
