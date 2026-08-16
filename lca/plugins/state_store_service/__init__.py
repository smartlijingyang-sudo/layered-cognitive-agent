"""State store service plugin — provides the ``state_store`` capability seam."""

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.state_store.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("state_store",),
)

name = "lca.state_store.service"
provides = "state_store"


def apply(ctx, config):
    from lca.layer0_infra.capability.state_store import StateStoreService
    from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

    service = StateStoreService()
    service.register("memory", InMemoryStateStore)
    ctx.mount("state_store", service)
