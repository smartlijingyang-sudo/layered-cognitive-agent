"""LLM Resolver plugin — sole owner of credentials, mode, and adapters.

Receives already-resolved ``api_key`` / ``base_url`` from the profile
resolver (``{from_env: ...}``). Does not read ``os.environ`` (ADR-0061 P3).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from lca.plugins._cordis_adapter import PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    mode: str = Field(default="auto", description="auto | real | mock | deepseek")
    default_model: str = Field(default="deepseek-chat")
    api_key: SecretStr | str | None = None
    base_url: str | None = None


def _secret_value(value: SecretStr | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
        return raw or None
    return value or None


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
        llm.providers.use("mock")


@plugin(
    id="lca-llm-resolver",
    requires=["llm"],
    provides=["llm_resolver"],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register LLM adapters and provide the resolver for /runs.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_llm_single_owner_without_key",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver, live_credential

    api_key = live_credential(_secret_value(config.api_key))
    base_url = live_credential(config.base_url)
    llm_svc = ctx.require("llm") if hasattr(ctx, "require") else ctx.inject("llm")
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
