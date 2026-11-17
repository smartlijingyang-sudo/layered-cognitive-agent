"""Mangli 企业级 Playground 离线自包含控制台路由插件。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

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
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.route.register import register_routes

_STATIC_DIR = Path(__file__).parent / "static"
_PLAYGROUND_HTML_PATH = _STATIC_DIR / "mangli_playground.html"


def _load_playground_html() -> str:
    if _PLAYGROUND_HTML_PATH.exists():
        return _PLAYGROUND_HTML_PATH.read_text(encoding="utf-8")
    return "<!DOCTYPE html><html><body><h1>Mangli Playground</h1></body></html>"


async def playground_endpoint(request: Request) -> Response:
    """提供纯内网离线自包含的 Playground 验证控制台单页。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    html_content = _load_playground_html()
    return HTMLResponse(
        content=html_content,
        status_code=200,
        headers=cors_headers(),
    )


PLAYGROUND_ROUTE_SPECS = (
    RouteSpec(
        "/playground",
        playground_endpoint,
        ("GET", "HEAD", "OPTIONS"),
    ),
)


@plugin(
    id="mangli-enterprise-playground-route",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Mangli 离线自包含 Playground 控制台路由插件",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("mangli-enterprise-playground-route.served",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("mangli_playground_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """挂载 /playground 验证单页路由。"""
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        PLAYGROUND_ROUTE_SPECS,
        plugin_id="mangli-enterprise-playground-route",
    )


__all__ = [
    "PLAYGROUND_ROUTE_SPECS",
    "playground_endpoint",
    "setup",
]
