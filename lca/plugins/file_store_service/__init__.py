"""File store service plugin — provides the ``file_store`` capability seam."""

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.file_store.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("file_store",),
)

name = "lca.file_store.service"
provides = "file_store"


def apply(ctx, config):
    from lca.layer0_infra.capability.files import FileStoreService
    from lca.layer0_infra.file_store import get_default_file_store

    service = FileStoreService()
    service.register("local", get_default_file_store())
    ctx.mount("file_store", service)
