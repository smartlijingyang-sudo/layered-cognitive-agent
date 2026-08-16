"""LLM service plugin — provides the ``llm`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.llm.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("llm",),
)

name = "lca.llm.service"
provides = "llm"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.llm import LlmService
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

    service = LlmService()
    service.register("mock", MockLLMAdapter())
    ctx.mount("llm", service)
