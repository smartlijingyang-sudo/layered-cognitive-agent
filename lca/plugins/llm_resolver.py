"""LLM Resolver plugin — sole owner of credentials, dotenv, and the chat adapter.

Loads project ``.env`` + normalizes Anthropic aliases, then registers exactly
one OpenAI-compat adapter on the ``llm`` seam. No product ``mode`` vocabulary
(mock / deepseek / auto). Tests inject a fake resolver via ``ctx.provide``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, SecretStr

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer0_infra.llm.config import DEFAULT_CHAT_MODEL

if TYPE_CHECKING:
    from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    default_model: str = Field(default=DEFAULT_CHAT_MODEL)
    api_key: SecretStr | str | None = None
    base_url: str | None = None
    openai_base_url: str | None = None
    api_style: str | None = None
    load_dotenv: bool = Field(
        default=True,
        description="Load project .env before reading LLM_* (sole credential owner).",
    )


def _secret_value(value: SecretStr | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
        return raw or None
    return value or None


def _parse_api_style(raw: str | None) -> LLMApiStyle | None:
    from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle

    if not raw:
        return None
    text = raw.strip().lower()
    for style in LLMApiStyle:
        if style.value == text or style.name.lower() == text:
            return style
    return None


@plugin(
    id="lca-llm-resolver",
    requires=["llm"],
    provides=["llm_resolver"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Load .env, register the chat LLM adapter, provide llm_resolver.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_llm_single_owner_without_key",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.llm.config import (
        LLMProviderSettings,
        normalize_llm_environ,
        prepare_llm_environ,
    )
    from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver, live_credential

    if config.load_dotenv:
        prepare_llm_environ()
    else:
        normalize_llm_environ()

    settings = LLMProviderSettings()
    api_key = live_credential(_secret_value(config.api_key)) or live_credential(settings.api_key)
    base_url = live_credential(config.base_url) or settings.agent_endpoint().base_url
    openai_base = live_credential(config.openai_base_url) or live_credential(
        settings.openai_base_url
    )
    model = (config.default_model or "").strip() or settings.configured_model()
    api_style = _parse_api_style(config.api_style) or _parse_api_style(settings.api_style)

    llm_svc = ctx.require("llm") if hasattr(ctx, "require") else ctx.inject("llm")
    if api_key:
        adapter = OpenAICompatAdapter(
            model=model,
            api_key=api_key,
            base_url=base_url,
            api=api_style,
        )
        llm_svc.register("default", adapter, activate=True)

    ctx.provide(
        "llm_resolver",
        ProductionLLMResolver(
            api_key=api_key,
            base_url=base_url,
            openai_base_url=openai_base,
            default_model=model,
            api_style=api_style.value if api_style is not None else None,
            llm_service=llm_svc,
        ),
    )
