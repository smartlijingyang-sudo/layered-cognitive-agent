"""LLM service plugin — mounts the ``llm`` capability Definition.

Service Definition role only (DSH ``llm/llm`` mirror): it owns the empty
provider table. Providers install adapters into it:
- ``lca.plugins.llm_provider`` registers the production adapter (or mock).
- Tests register mock adapters directly.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest, ProviderMode

manifest = PluginManifest(
    id="lca.llm.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("llm",),
    provider_mode=ProviderMode.REGISTRY,
)

name = "lca.llm.service"
provides = "llm"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.llm import LlmService

    service = LlmService()
    ctx.mount("llm", service)
