"""HTTP /lca-api/channels/wechat/* — WeChat channel management and auth routes."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.channels.wechat import WechatChannelConfig
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
from lca.infrastructure.channels.wechat.client import WechatIlinkClient
from lca.infrastructure.channels.wechat.manager import WechatChannelManager
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.route.register import register_routes


def _get_client(request: Request) -> WechatIlinkClient:
    client = getattr(request.app.state, "wechat_client", None)
    if client is None:
        client = WechatIlinkClient()
        request.app.state.wechat_client = client
    return client


def _get_manager(request: Request) -> WechatChannelManager:
    manager = getattr(request.app.state, "wechat_manager", None)
    if manager is None:
        manager = WechatChannelManager()
        request.app.state.wechat_manager = manager
    return manager


async def wechat_qrcode(request: Request) -> Response:
    """Fetch QR code payload for WeChat iLink login."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    client = _get_client(request)
    try:
        result = await client.fetch_qrcode()
        return JSONResponse(result.model_dump(), headers=cors_headers())
    except Exception as exc:
        return JSONResponse(
            {"error": "Failed to fetch WeChat QR code", "detail": str(exc)},
            status_code=502,
            headers=cors_headers(),
        )


async def wechat_status(request: Request) -> Response:
    """Poll QR code status."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    qrcode = request.query_params.get("qrcode")
    if not qrcode:
        return JSONResponse(
            {"error": "Missing required query parameter: qrcode"},
            status_code=400,
            headers=cors_headers(),
        )

    client = _get_client(request)
    try:
        result = await client.poll_qrcode_status(qrcode)
        return JSONResponse(result.model_dump(), headers=cors_headers())
    except Exception as exc:
        return JSONResponse(
            {"error": "Failed to poll WeChat status", "detail": str(exc)},
            status_code=502,
            headers=cors_headers(),
        )


async def wechat_bind(request: Request) -> Response:
    """Bind an Assistant to a WeChat channel and start worker."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    try:
        body = await request.json()
    except Exception:
        body = {}

    assistant_id = body.get("assistant_id")
    if not assistant_id:
        return JSONResponse(
            {"error": "Missing required field: assistant_id"},
            status_code=400,
            headers=cors_headers(),
        )

    bot_id = body.get("bot_id")
    bot_token = body.get("bot_token")
    user_id = body.get("user_id")

    if not bot_id or not bot_token or not user_id:
        return JSONResponse(
            {"error": "Missing required credentials (bot_id, bot_token, user_id)"},
            status_code=400,
            headers=cors_headers(),
        )

    config = WechatChannelConfig(
        bot_id=bot_id,
        bot_token=bot_token,
        user_id=user_id,
        base_url=body.get("base_url", "https://ilinkai.weixin.qq.com"),
        enabled=body.get("enabled", True),
        display_tool_calls=body.get("display_tool_calls", False),
    )

    manager = _get_manager(request)
    await manager.bind_channel(assistant_id, config)

    return JSONResponse(
        {"ok": True, "assistant_id": assistant_id},
        headers=cors_headers(),
    )


async def wechat_unbind(request: Request) -> Response:
    """Unbind an Assistant from WeChat channel and stop worker."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    try:
        body = await request.json()
    except Exception:
        body = {}

    assistant_id = body.get("assistant_id")
    if not assistant_id:
        return JSONResponse(
            {"error": "Missing required field: assistant_id"},
            status_code=400,
            headers=cors_headers(),
        )

    manager = _get_manager(request)
    await manager.unbind_channel(assistant_id)

    return JSONResponse(
        {"ok": True, "assistant_id": assistant_id},
        headers=cors_headers(),
    )


async def wechat_config(request: Request) -> Response:
    """Get active WeChat channel configuration and running status for an Assistant."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    assistant_id = request.query_params.get("assistant_id")
    if not assistant_id:
        return JSONResponse(
            {"error": "Missing required query parameter: assistant_id"},
            status_code=400,
            headers=cors_headers(),
        )

    manager = _get_manager(request)
    config = manager.get_channel_config(assistant_id)
    is_running = manager.is_running(assistant_id)

    return JSONResponse(
        {
            "assistant_id": assistant_id,
            "is_running": is_running,
            "config": config.model_dump() if config else None,
        },
        headers=cors_headers(),
    )


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/channels/wechat/qrcode", wechat_qrcode, ("GET", "OPTIONS")),
    RouteSpec("/channels/wechat/status", wechat_status, ("GET", "OPTIONS")),
    RouteSpec("/channels/wechat/bind", wechat_bind, ("POST", "OPTIONS")),
    RouteSpec("/channels/wechat/unbind", wechat_unbind, ("POST", "OPTIONS")),
    RouteSpec("/channels/wechat/config", wechat_config, ("GET", "OPTIONS")),
    RouteSpec("/lca-api/channels/wechat/qrcode", wechat_qrcode, ("GET", "OPTIONS")),
    RouteSpec("/lca-api/channels/wechat/status", wechat_status, ("GET", "OPTIONS")),
    RouteSpec("/lca-api/channels/wechat/bind", wechat_bind, ("POST", "OPTIONS")),
    RouteSpec("/lca-api/channels/wechat/unbind", wechat_unbind, ("POST", "OPTIONS")),
    RouteSpec("/lca-api/channels/wechat/config", wechat_config, ("GET", "OPTIONS")),
)


@plugin(
    id="lca-gateway-routes-channels-wechat",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /lca-api/channels/wechat/* routes.",
    test_suite="tests.transport.test_routes_channels_wechat",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-channels-wechat.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_wechat_channel_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-gateway-routes-channels-wechat")
