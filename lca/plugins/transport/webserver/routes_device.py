"""Register ``/api/device/*`` route family (PR-4 routes-device + ADR-0163 决策 5).

Declarative :class:`RouteSpec` catalog shared with the rest of the
transport route plugins via :func:`register_routes`. The
``device_hub`` capability gates this family: when it is absent the
family is silent (no 503 down the line).
"""

from __future__ import annotations

from typing import Any

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
from lca.plugins.transport.device_hub.routes import (
    agent_run,
    connect_device,
    device_status,
    list_devices,
    rpc,
    system_info,
    tool_call,
    upload_files,
)
from lca.plugins.transport.webserver.route_register import register_routes

ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/api/device/status", device_status, ("POST", "OPTIONS")),
    RouteSpec("/api/device/devices", list_devices, ("POST", "OPTIONS")),
    RouteSpec("/api/device/tool-call", tool_call, ("POST", "OPTIONS")),
    RouteSpec("/api/device/system-info", system_info, ("POST", "OPTIONS")),
    RouteSpec("/api/device/rpc", rpc, ("POST", "OPTIONS")),
    RouteSpec("/api/device/agent/run", agent_run, ("POST", "OPTIONS")),
    RouteSpec("/api/device/files/upload", upload_files, ("POST", "OPTIONS")),
)

# WebSocket path stays literal:RouteSpec is HTTP-only.
_WS_PATH = "/api/device/ws"


@plugin(
    id="lca-gateway-routes-device",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /api/device/* (7 HTTP + 1 WebSocket) routes.",
    test_suite="tests.lca_plugins.transport.webserver.test_device",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-device.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_device_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-gateway-routes-device")

    # WebSocket:RouteSpec covers HTTP only;register it via the same registry
    # primitive so disposal still flows through ``ctx.effect``.
    from starlette.routing import WebSocketRoute

    ws_dispose = registry.register_websocket(WebSocketRoute(_WS_PATH, connect_device))
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(ws_dispose, label=f"ws:{_WS_PATH}")
