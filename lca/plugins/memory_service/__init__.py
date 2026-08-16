"""Memory service plugin — provides the ``memory`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.memory.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("memory",),
)

name = "lca.memory.service"
provides = "memory"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.memory import MemoryService
    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

    service = MemoryService()
    service.register("simple", SimpleMemorySystem)
    ctx.mount("memory", service)
