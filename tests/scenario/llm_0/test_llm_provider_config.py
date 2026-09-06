"""Tests for LLM provider settings — env vars drive model/key/url/limits."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from lca.infrastructure.llm.config import LLMProviderSettings, normalize_llm_environ


@contextmanager
def _env(**values: str) -> Iterator[None]:
    saved = dict((k, os.environ.get(k)) for k in values)  # noqa: C402 - restore each configured key
    try:
        os.environ.update(dict(values))
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_settings_ignore_empty_openai_url() -> None:
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
        "LLM_OPENAI_BASE_URL": "",
    }
    with _env(**env):
        settings = LLMProviderSettings()
        assert settings.openai_base_url == ""
        assert settings.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic"


def test_agent_endpoint_uses_configured_model_and_base_url() -> None:
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
    }
    with _env(**env):
        normalize_llm_environ()
        settings = LLMProviderSettings()
        endpoint = settings.agent_endpoint()
        assert endpoint.model == "qwen3.7-plus"
        assert endpoint.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
        assert endpoint.api_key == "sk-shared"


def test_provider_config_exposes_shared_values() -> None:
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
    }
    with _env(**env):
        settings = LLMProviderSettings()
        assert settings.configured_model() == "qwen3.7-plus"
        assert settings.api_key == "sk-shared"
        assert settings.openai_base_url == "https://coding.dashscope.aliyuncs.com/v1"
