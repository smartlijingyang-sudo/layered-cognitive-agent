"""LLM provider config is the single source for model, key, and faces."""

from __future__ import annotations

import os
from unittest import mock

from lca.layer0_infra.llm.config import (
    LLMFace,
    LLMProviderSettings,
    configured_chat_model,
    resolve_endpoint,
)
from lca.layer0_infra.llm_resolver import llm_credentials, llm_openai_credentials


def _env(**kwargs: str) -> mock._patch:
    return mock.patch.dict(os.environ, kwargs, clear=False)


def test_agent_and_compat_share_the_same_model() -> None:
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
        "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
    }
    with _env(**env):
        agent = resolve_endpoint(LLMFace.AGENT)
        compat = resolve_endpoint(LLMFace.OPENAI_COMPAT)
        assert agent.model == compat.model == "qwen3.7-plus"
        assert agent.api_key == compat.api_key == "sk-shared"
        assert agent.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
        assert compat.base_url == "https://coding.dashscope.aliyuncs.com/v1"
        assert configured_chat_model() == "qwen3.7-plus"


def test_legacy_tuples_read_the_same_config() -> None:
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
        "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
    }
    with _env(**env):
        assert llm_credentials() == (
            "sk-shared",
            "https://coding.dashscope.aliyuncs.com/apps/anthropic",
            "qwen3.7-plus",
        )
        assert llm_openai_credentials() == (
            "sk-shared",
            "https://coding.dashscope.aliyuncs.com/v1",
            "qwen3.7-plus",
        )


def test_dsh_reads_provider_config_not_its_own_model() -> None:
    from lca.layer0_infra.dsh.settings import DshSettings

    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
        "LLM_MAX_TOKENS": "4096",
    }
    with _env(**env):
        settings = DshSettings()
        assert settings.resolved_model() == configured_chat_model() == "qwen3.7-plus"
        assert settings.resolved_api_key() == "sk-shared"
        assert settings.resolved_base_url() == "https://coding.dashscope.aliyuncs.com/v1"
        assert settings.resolved_max_tokens() == 4096


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
        assert resolve_endpoint(LLMFace.OPENAI_COMPAT).base_url is None
