"""Register the ``/health`` + OPTIONS handlers (PR-4 routes-health-options).

handler 内部继续复用 ``gateway.runs.api.routes`` 现有实现;本 PR 只关注
plugin 化路由注册,不重构 handler 内部(留给 PR-5 清理跨层 import)。
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.cors import CORS_HEADERS
from gateway.runs.api.query_endpoints import get_context, health_payload, stream_journal_live
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


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(request: Request) -> JSONResponse:
    payload = health_payload(
        request.app.state.run_port,
        ctx=getattr(request.app.state, "ctx", None),
    )
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


# PR-7:展平为 module-level ``ROUTES`` (无下划线),``build_routes`` 退役后
# 测试与 ``gateway.app`` 直接 import 这个常量验证 route catalog。
ROUTES: tuple[Route, ...] = (
    Route("/health", health, methods=["GET"]),
    Route("/context", get_context, methods=["GET", "OPTIONS"]),
    Route("/journal/live", stream_journal_live, methods=["GET", "OPTIONS"]),
)


@plugin(
    id="lca-gateway-routes-health-options",
    provides=("gateway_health_options_route",),
    requires=("gateway_router",),
    layer="L3",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /health + OPTIONS for /context and /journal/live.",
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
        reads=("gateway_router",),
        emits=("gateway_health_options_route.registered",),
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
