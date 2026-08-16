"""Observability service plugin — provides the ``observability`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.observability.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("observability",),
)

name = "lca.observability.service"
provides = "observability"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.observability import ObservabilityService
    from lca.layer0_infra.observability.registry import create_observability

    service = ObservabilityService()
    service.register("console", lambda: create_observability("console"))
    ctx.mount("observability", service)
