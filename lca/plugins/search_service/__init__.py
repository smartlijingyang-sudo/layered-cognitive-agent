"""Search service plugin — provides the ``search`` capability seam."""

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


def apply(ctx, config):
    from lca.layer0_infra.capability.search import SearchService
    from lca.layer0_infra.search.providers.tavily import search_tavily

    service = SearchService()
    service.register("tavily", search_tavily)
    ctx.mount("search", service)
