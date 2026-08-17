"""LLM provider plugin — installs the production OpenAI-compatible adapter.

This is the **Provider** role of the ``llm`` seam (DSH ``llm-deepseek``
mirror). The Service Definition is ``LlmService`` (mounted by
``lca.plugins.llm_service``); this plugin registers the real network adapter
into its provider table, or the deterministic mock when no key is present.

Every registration is an effect: the returned disposer uninstalls the
adapter when the plugin unloads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.llm.provider",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.PROVIDER,
    requires=("llm",),
    provides=(),
)

name = "lca.llm.provider"
inject = ("llm",)


class Config(BaseModel):
    """Provider selection: ``real`` (env) or ``mock`` (offline deterministic)."""

    mode: Literal["auto", "real", "mock"] = "auto"
    """auto = real when LLM_API_KEY present, else mock; real | mock force."""

    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

    raw = config.model_dump() if hasattr(config, "model_dump") else (config or {})
    mode = str(raw.get("mode") or "auto")
    service = ctx.require("llm")

    key = raw.get("api_key")
    base = raw.get("base_url")
    model = raw.get("model")

    if mode == "mock" or (mode == "auto" and not _env_key(key)):
        provider = MockLLMAdapter()
        disposer = service.register("mock", provider, activate=True)
        ctx.effect(lambda: disposer, "ctx.mount(llm.provider=mock)")
        return

    from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

    provider = OpenAICompatAdapter(model=model, api_key=key, base_url=base)
    disposer = service.register("real", provider, activate=True)
    ctx.effect(lambda: disposer, "ctx.mount(llm.provider=real)")


def _env_key(explicit: str | None) -> bool:
    import os

    return bool(explicit) or bool(os.getenv("LLM_API_KEY"))
