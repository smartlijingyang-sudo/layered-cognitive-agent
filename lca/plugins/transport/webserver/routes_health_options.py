"""Register the ``/health`` + OPTIONS handlers (PR-4 + ADR-0163 决策 3).

Declarative :class:`RouteSpec` catalog. ``/journal/live`` declares the
``process_journal`` capability as **optional**; when the capability is
absent on the boot ``ctx`` the spec is skipped and Starlette returns 404
for the path. No 503 down the line.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.cors import CORS_HEADERS
from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    get_context,
    health_payload,
    stream_journal_live,
)
from lca.plugins.transport.webserver.route_register import register_routes


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(request: Request) -> JSONResponse:
    payload = health_payload(
        request.app.state.run_port,
        ctx=getattr(request.app.state, "ctx", None),
    )
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/health", health, ("GET",)),
    RouteSpec("/context", get_context, ("GET", "OPTIONS")),
    RouteSpec(
        "/journal/live",
        stream_journal_live,
        ("GET", "OPTIONS"),
        optional=("process_journal",),
    ),
)


@plugin(
    id="lca-gateway-routes-health-options",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /health + OPTIONS for /context + optional /journal/live.",
    test_suite="tests.lca_plugins.transport.webserver.test_routes_health_options",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-health-options.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_health_options_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    register_routes(
        registry, ctx, ROUTE_SPECS, plugin_id="lca-gateway-routes-health-options"
    )
