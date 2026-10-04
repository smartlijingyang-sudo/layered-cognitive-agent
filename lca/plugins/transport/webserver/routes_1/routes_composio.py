"""Register Composio OAuth callback + connection REST routes."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.composio import endpoints as composio_handlers
from lca.plugins.transport.webserver.route.register import register_routes

ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/composio/oauth/callback", composio_handlers.oauth_callback, ("GET",)),
    RouteSpec("/composio/connections", composio_handlers.connections, ("GET", "POST", "OPTIONS")),
    RouteSpec(
        "/composio/connections/by-account/{connected_account_id}",
        composio_handlers.connection_by_account,
        ("GET", "OPTIONS"),
    ),
    RouteSpec(
        "/composio/connections/{identifier}/refresh",
        composio_handlers.connection_refresh,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/composio/connections/{identifier}",
        composio_handlers.connection_by_identifier,
        ("DELETE", "OPTIONS"),
    ),
    RouteSpec(
        "/composio/auth-intents/{intent_id}/resolve",
        composio_handlers.resolve_auth_intent,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/api/connectors/auth-intents/{intent_id}/resolve",
        composio_handlers.resolve_auth_intent,
        ("POST", "OPTIONS"),
    ),
)


@plugin(
    id="lca-gateway-routes-composio",
    provides=(),
    requires=("route_registry", "composio"),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /composio/oauth/callback and connection management REST routes.",
    test_suite="tests/lca_plugins/transport/webserver/test_routes_composio.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-composio.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry", "composio"),
        emits=("gateway_composio_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    # The composio provider plugin declares provides=["composio"] but skips
    # the binding when unconfigured (no API key). Skip route registration
    # instead of crashing boot with KeyError.
    try:
        integration = ctx.require("composio")
    except (KeyError, LookupError):
        return
    composio_handlers.bind_composio(integration)
    registry = ctx.require("route_registry")
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-gateway-routes-composio")
