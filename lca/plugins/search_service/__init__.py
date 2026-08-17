"""Search service plugin — provides the ``search`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.search.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("search",),
)

name = "lca.search.service"
provides = "search"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.search import SearchService
    from lca.layer0_infra.search.providers.tavily import search_tavily

    service = SearchService()
    disposer = service.register("tavily", search_tavily)
    ctx.effect(lambda: disposer, "ctx.register(search.provider=tavily)")
    ctx.mount("search", service)
