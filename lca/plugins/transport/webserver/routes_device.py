"""Register ``/api/device/*`` route family (PR-4 routes-device).

handler 内部继续复用 ``gateway.device_gateway.routes`` 现有实现;本 PR
只 plugin 化路由注册,不重构 handler 内部(留给 PR-5 清理跨层 import)。
"""

from __future__ import annotations

from typing import Any

from starlette.routing import Route, WebSocketRoute

from gateway.device_gateway.routes import (
    agent_run,
    connect_device,
    device_status,
    list_devices,
    rpc,
    system_info,
    tool_call,
    upload_files,
)
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

ROUTES: tuple[Route, ...] = (
    Route("/api/device/status", device_status, methods=["POST", "OPTIONS"]),
    Route("/api/device/devices", list_devices, methods=["POST", "OPTIONS"]),
    Route("/api/device/tool-call", tool_call, methods=["POST", "OPTIONS"]),
    Route("/api/device/system-info", system_info, methods=["POST", "OPTIONS"]),
    Route("/api/device/rpc", rpc, methods=["POST", "OPTIONS"]),
    Route("/api/device/agent/run", agent_run, methods=["POST", "OPTIONS"]),
    Route("/api/device/files/upload", upload_files, methods=["POST", "OPTIONS"]),
)
UPGRADE: WebSocketRoute = WebSocketRoute("/api/device/ws", connect_device)


@plugin(
    id="lca-gateway-routes-device",
    provides=("gateway_device_route",),
    requires=("gateway_router",),
    layer="L3",
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
        reads=("gateway_router",),
        emits=("gateway_device_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    router = ctx.require("gateway_router")
    # PluginContext Protocol does not expose ``effect()``;the underlying
    # :class:`cordis.Context` does. Reach it through the audited facade.
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    for route in ROUTES:
        dispose = router.register_http(route)
        inner.effect(dispose, label=f"route:{route.path}")
    ws_dispose = router.register_websocket(UPGRADE)
    inner.effect(ws_dispose, label=f"ws:{UPGRADE.path}")
