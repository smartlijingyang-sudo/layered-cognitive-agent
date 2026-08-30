"""LLM Resolver plugin — sole owner of credentials and the chat adapter.

The resolver loads project ``.env`` + normalizes aliases, then registers one
profile-selected adapter on the ``llm`` seam.  When fallback candidates are
configured, that adapter is a failover wrapper around OpenAI-compatible
providers; the agent loop still owns no provider-specific branching.  Tests
inject a fake resolver via ``ctx.provide``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, SecretStr

from lca.contracts.protocols import LLMAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer0_infra.llm.config import DEFAULT_CHAT_MODEL

if TYPE_CHECKING:
    from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle


class FallbackConfig(BaseModel):
    """One lower-priority OpenAI-compatible provider candidate.

    Omitted endpoint, credential, and API-style fields inherit the resolved
    primary values.  This keeps all credential resolution inside the sole LLM
    resolver plugin while allowing a profile to select an ordered model chain.
    """

    model_config = {"extra": "forbid"}
    model: str = Field(min_length=1)
    api_key: SecretStr | str | None = None
    base_url: str | None = None
    api_style: str | None = None


class RetryConfig(BaseModel):
    """Bounded retry policy applied independently to every configured candidate."""

    model_config = {"extra": "forbid"}
    max_attempts: int = Field(default=1, ge=1)
    initial_backoff_seconds: float = Field(default=0.0, ge=0.0)
    max_backoff_seconds: float | None = Field(default=None, ge=0.0)


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    default_model: str = Field(default=DEFAULT_CHAT_MODEL)
    api_key: SecretStr | str | None = None
    base_url: str | None = None
    openai_base_url: str | None = None
    api_style: str | None = None
    retry: RetryConfig = Field(default_factory=RetryConfig)
    fallbacks: tuple[FallbackConfig, ...] = ()
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
    Config=Config,
    requires=["llm"],
    provides=["llm_resolver"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Load .env, register a Profile-selected resilient chat adapter, provide llm_resolver.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_llm_single_owner_without_key",
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    from lca.layer0_infra.llm.config import (
        LLMProviderSettings,
        normalize_llm_environ,
        prepare_llm_environ,
    )
    from lca.layer0_infra.llm_adapter.failover import (
        FailoverLLMAdapter,
        LLMFailoverCandidate,
        LLMRetryPolicy,
        RetryingLLMAdapter,
    )
    from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver, live_credential

    if not isinstance(config, Config):
        raise TypeError("LLM resolver config must be Config")
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

    llm_svc = ctx.require("llm")
    retry_policy = LLMRetryPolicy(
        max_attempts=config.retry.max_attempts,
        initial_backoff_seconds=config.retry.initial_backoff_seconds,
        max_backoff_seconds=config.retry.max_backoff_seconds,
    )

    def _with_retry(adapter: LLMAdapter) -> LLMAdapter:
        if retry_policy.max_attempts == 1:
            return adapter
        return RetryingLLMAdapter(adapter, retry_policy)

    candidates: list[LLMFailoverCandidate] = []
    if api_key:
        candidates.append(
            LLMFailoverCandidate(
                name="primary",
                adapter=_with_retry(
                    OpenAICompatAdapter(
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        api=api_style,
                    )
                ),
            )
        )
    for index, fallback in enumerate(config.fallbacks, start=1):
        fallback_key = live_credential(_secret_value(fallback.api_key)) or api_key
        if fallback_key is None:
            continue
        fallback_model = fallback.model.strip()
        if not fallback_model:
            raise ValueError(f"fallback #{index} model must not be blank")
        fallback_style = _parse_api_style(fallback.api_style) or api_style
        candidates.append(
            LLMFailoverCandidate(
                name=f"fallback-{index}",
                adapter=_with_retry(
                    OpenAICompatAdapter(
                        model=fallback_model,
                        api_key=fallback_key,
                        base_url=live_credential(fallback.base_url) or base_url,
                        api=fallback_style,
                    )
                ),
            )
        )
    if candidates:
        adapter = candidates[0].adapter if len(candidates) == 1 else FailoverLLMAdapter(candidates)
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


__all__ = ["Config", "FallbackConfig", "RetryConfig", "setup"]
