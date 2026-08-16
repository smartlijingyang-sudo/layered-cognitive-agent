"""Starlette HTTP/SSE carrier plugin for Harness command routes."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.gateway.starlette",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.CONSUMER,
    requires=("sessions", "projections"),
)


def apply(ctx: Any, config: dict[str, Any]) -> None:
    """Expose the carrier routes without importing a concrete agent loop."""
    from lca.plugins.gateway_starlette.session_routes import create_session_router

    ctx.mount("gateway_starlette_router_factory", create_session_router)
