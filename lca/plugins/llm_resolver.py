"""LLM Resolver plugin — sole owner of credentials, mode, and adapters.

Reads LLM_API_KEY / LLM_BASE_URL, registers adapters on ``ctx.llm``,
activates mock when no live key is present, and provides the resolver
``/runs`` injects. Unresolved ``${ENV}`` placeholders are not keys.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    mode: str = Field(default="auto", description="auto | real | mock | deepseek")
    api_key_env: str = Field(default="LLM_API_KEY")
    base_url_env: str = Field(default="LLM_BASE_URL")
    default_model: str = Field(default="deepseek-chat")
    api_key: str | None = None
    base_url: str | None = None


def _register_adapters(
    llm: object,
    *,
    mode: str,
    api_key: str | None,
    base_url: str | None,
    default_model: str,
) -> None:
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
    from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

    target = mode.strip().lower()
    if target == "auto":
        target = "real" if api_key else "mock"
    llm.register("mock", MockLLMAdapter(), activate=(target == "mock"))
    if api_key:
        llm.register(
            "real",
            OpenAICompatAdapter(api_key=api_key, base_url=base_url, model=default_model),
            activate=(target == "real"),
        )
        deepseek_base = base_url or "https://api.deepseek.com"
        llm.register(
            "deepseek",
            OpenAICompatAdapter(api_key=api_key, base_url=deepseek_base, model=default_model),
            activate=(target == "deepseek"),
        )
    elif target in {"real", "deepseek"}:
        # Mode asked for a live adapter but no live key — stay on mock.
        llm.providers.use("mock")


@plugin(
    name="lca-llm-resolver",
    requires=["llm"],
    provides=["llm_resolver"],
    layer="provider",
    side_effects="none",
    policy_class="control",
    description="Register LLM adapters and provide the resolver for /runs.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_llm_single_owner_without_key",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver, live_credential

    api_key = live_credential(config.api_key) or live_credential(os.environ.get(config.api_key_env))
    base_url = live_credential(config.base_url) or live_credential(
        os.environ.get(config.base_url_env)
    )
    llm_svc = ctx.inject("llm")
    _register_adapters(
        llm_svc,
        mode=config.mode,
        api_key=api_key,
        base_url=base_url,
        default_model=config.default_model,
    )
    ctx.provide(
        "llm_resolver",
        ProductionLLMResolver(
            mode=config.mode,
            api_key=api_key,
            base_url=base_url,
            default_model=config.default_model,
            llm_service=llm_svc,
        ),
    )
