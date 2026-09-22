"""HTTP /lca-api/channels/wechat/* — WeChat channel management and auth routes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
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
from lca.infrastructure.channels.wechat.formatter import WechatMessageFormatter
from lca.infrastructure.channels.wechat.manager import WechatChannelManager
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest
from lca.plugins.transport.webserver.read.runs.identity.identity import AgentRef
from lca.plugins.transport.webserver.route.register import register_routes

logger = logging.getLogger(__name__)


def _mask_secret(val: str | None) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "******"
    return f"{val[:3]}****{val[-4:]}"


def _extract_latest_progress(spine_path: Path) -> tuple[str | None, dict[str, Any] | None]:
    latest_thought = None
    latest_tool = None
    with open(spine_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            ep = rec.get("execution_point")
            p = rec.get("payload") or {}
            if ep == "llm.stream.token" and p.get("channel_kind") == "thought":
                latest_thought = p.get("text_delta")
            elif ep == "step.tool_call.record":
                tool_name = p.get("tool_name", "tool")
                latest_tool = {
                    "identifier": "system",
                    "api_name": tool_name,
                    "summary_arg": str(p.get("arguments", ""))[:40],
                }
    return latest_thought, latest_tool


async def wechat_gateway_dispatch(
    app: Any,
    assistant_id: str,
    session_id: str,
    user_text: str,
    progress_callback: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Dispatches a WeChat message to the LCA cognitive engine via RunPort."""
    run_port = getattr(app.state, "run_port", None)
    registry = getattr(app.state, "registry", None)
    ctx = getattr(app.state, "ctx", None)

    if run_port is None or registry is None:
        logger.warning("WeChat dispatch fallback: run_port or registry not available on app.state")
        return f"[{assistant_id}] 收到微信消息: {user_text}"

    agent_ref = AgentRef(agent_id=assistant_id)
    run_request = RunRequest(
        profile="web-assistant",
        question=user_text,
        user_text=user_text,
        mode="solo",
        attachment_ids=(),
        prior_turns=(),
        agent=agent_ref,
        device_id="",
        plane="",
        extra_plane="",
        execution_target="",
        options={},
        ctx=ctx,
        assistant_id=assistant_id,
    )

    receipt = await run_port.create_and_dispatch(run_request)
    if not receipt.accepted:
        return "抱歉，助理当前正忙或无法创建执行任务，请稍后重试。"

    session = registry.get(receipt.run_id)
    if session is None or session.task is None:
        return "抱歉，助理执行初始化失败。"

    spine_path = Path("traces") / "runs" / receipt.run_id / f"{receipt.run_id}.spine.jsonl"
    last_thought = ""
    last_tool = ""

    while not session.task.done():
        await asyncio.sleep(0.3)
        if progress_callback and spine_path.exists():
            with contextlib.suppress(Exception):
                th, tl = _extract_latest_progress(spine_path)
                if th and th != last_thought:
                    last_thought = th
                    msg = WechatMessageFormatter.format_step_progress(
                        step_type="thinking",
                        thinking_text=th,
                    )
                    await progress_callback(msg)
                if tl and tl != last_tool:
                    last_tool = tl
                    msg = WechatMessageFormatter.format_step_progress(
                        step_type="tools_calling",
                        tools_calling=[tl],
                    )
                    await progress_callback(msg)

    try:
        await session.task
    except Exception as exc:
        logger.exception("Error executing run %s for wechat: %s", receipt.run_id, exc)
        return "抱歉，助理在处理该请求时遇到了内部错误，请稍后重试。"

    # Check for approval / waiting input
    status_val = getattr(session.status, "value", str(session.status))
    if status_val == "waiting_input":
        req = getattr(session, "approval_request", None) or {}
        q = req.get("question") or req.get("description") or "该操作涉及审批，需要人工审批确认。"
        return f"【需要审批】{q}"

    # Extract final answer from spine
    if not spine_path.exists():
        return getattr(session, "error", None) or "执行完成。"

    output_chunks: list[str] = []
    with open(spine_path, encoding="utf-8") as f:  # noqa: ASYNC230
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if rec.get("execution_point") == "llm.stream.token":
                p = rec.get("payload") or {}
                if p.get("channel_kind") == "output":
                    output_chunks.append(p.get("text_delta", ""))

    reply = "".join(output_chunks).strip()
    if not reply:
        err = getattr(session, "error", None)
        reply = f"执行异常: {err}" if err else "已处理完成。"
    return reply


def _get_client(request: Request) -> WechatIlinkClient:
    client = getattr(request.app.state, "wechat_client", None)
    if client is None:
        client = WechatIlinkClient()
        request.app.state.wechat_client = client
    return client


def _get_manager(request: Request) -> WechatChannelManager:
    manager = getattr(request.app.state, "wechat_manager", None)
    if manager is None:
        manager = WechatChannelManager(
            client_factory=lambda base_url: WechatIlinkClient(base_url=base_url),
            dispatch_fn=lambda asst_id, sess_id, text, cb=None: wechat_gateway_dispatch(
                request.app, asst_id, sess_id, text, cb
            ),
        )
        request.app.state.wechat_manager = manager
        with contextlib.suppress(RuntimeError):
            load_task = asyncio.create_task(manager.load_all_channels())
            request.app.state._wechat_channel_load_task = load_task
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

    bot_id = body.get("bot_id") or body.get("ilink_bot_id")
    bot_token = body.get("bot_token")
    user_id = body.get("user_id") or body.get("ilink_user_id")
    if not bot_id or not bot_token or not user_id:
        return JSONResponse(
            {"error": "Missing required credentials (bot_id, bot_token, user_id)"},
            status_code=400,
            headers=cors_headers(),
        )

    base_url = body.get("base_url") or body.get("baseurl") or "https://ilinkai.weixin.qq.com"
    config = WechatChannelConfig(
        bot_id=bot_id,
        bot_token=bot_token,
        user_id=user_id,
        base_url=base_url,
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

    cfg_dict = config.model_dump() if config else None
    if cfg_dict and "bot_token" in cfg_dict:
        cfg_dict["bot_token"] = _mask_secret(cfg_dict["bot_token"])

    return JSONResponse(
        {
            "assistant_id": assistant_id,
            "is_running": is_running,
            "config": cfg_dict,
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
