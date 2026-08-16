"""Sandbox service plugin — provides the ``sandbox`` capability seam."""

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.sandbox.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("sandbox",),
)

name = "lca.sandbox.service"
provides = "sandbox"


def apply(ctx, config):
    from lca.layer0_infra.capability.sandbox import SandboxService
    from lca.layer0_infra.sandbox.factory import resolve_sandbox

    service = SandboxService()
    resolved = resolve_sandbox()
    if resolved is not None:
        service.register("active", resolved, activate=True)
    ctx.mount("sandbox", service)
