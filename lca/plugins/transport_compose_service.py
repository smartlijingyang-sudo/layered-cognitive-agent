"""Transport Compose Service plugin — named factory ``transport.compose_service``.

Returns a fresh :class:`TransportService` per composition (per-compose
transport table; one per agent pipeline). Composer no longer instantiates
``TransportService()`` inline; it resolves a factory through this plugin.
"""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols.infra import TransportRegistryProtocol
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_transport_service_compose() -> TransportRegistryProtocol:
    from lca.layer0_infra.capability.transport import TransportService

    return TransportService()


@plugin(
    id="transport.compose_service",
    provides=["transport.compose_service"],
    requires=[],
    implements=[TransportRegistryProtocol],
    layer="L1",
    effects="none",
    description="Compose-time TransportService factory (one fresh instance per compose).",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide the named factory ``transport.compose_service``."""
    ctx.provide("transport.compose_service", build_transport_service_compose)
