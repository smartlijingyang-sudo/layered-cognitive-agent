"""Tools service plugin — provides the ``tools`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.tools.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("tools",),
)

name = "lca.tools.service"
provides = "tools"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.tools import ToolsService

    service = ToolsService()
    ctx.mount("tools", service)
