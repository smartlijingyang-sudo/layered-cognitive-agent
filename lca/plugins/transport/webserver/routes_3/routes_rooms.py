"""Register ``/v1/rooms`` REST surface —— 群聊房间运行时（Room Runtime Go-Live M1）。

Endpoints:

- ``POST /v1/rooms`` …… 创建房间（RoomSpec）
- ``GET  /v1/rooms`` …… 列出房间
- ``GET  /v1/rooms/{room_id}`` …… 获取单个房间（不存在 404）
- ``POST /v1/rooms/{room_id}/messages`` …… 发消息并触发真实 run 分发
- ``GET  /v1/rooms/{room_id}/messages`` …… 列出房间转录

``/v1/rooms`` 与 ``/v1/rooms/{room_id}/messages`` 分别由
:func:`rooms_root` / :func:`room_messages_root` 做 method dispatch
（POST + GET 共享 path，RouteRegistry 不允许重复 path）。

``run_starter`` 在路由层接线到 ``RunPort``：``prepare_run_from_messages``
解析消息 → ``parse_agent_ref`` 解析身份 → ``resolve_profile_mode`` 解析
模式 → ``RunRequest`` → ``create_and_dispatch`` → ``register_gateway_run``
让 run 进入 gateway 流（对齐 ``command_endpoints.create_run``）。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.application.collaboration.room_dispatch import (
    RoomDispatcher,
    RoomNotFoundError,
    RunDispatchResult,
    RunOutcome,
)
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
from lca.contracts.models.collaboration.peer import RoomSpec
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.domain.collaboration.room import JsonRoomMessageStore, JsonRoomRepository
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.gateway_lifecycle import (
    register_gateway_run,
)
from lca.plugins.transport.webserver.route.register import register_routes


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=cors_headers())


def _error(message: str, *, status_code: int, code: str) -> JSONResponse:
    return _json({"error": {"code": code, "message": message}}, status_code=status_code)


async def _start_run(
    request: Request,
    *,
    room_id: str,
    objective: str,
    mode: str,
    correlation_id: str,
    coordinator_agent_id: str | None = None,
    selected_peers: tuple[str, ...] | None = None,
) -> RunDispatchResult:
    """Wire ``RoomDispatcher`` to the real ``RunPort`` (aligns with create_run).

    ``command_endpoints`` is imported at module level so the ``handlers.runs.api``
    package loads in the same order as the existing routes plugins, avoiding the
    ``ingress ↔ api`` circular import.
    """
    ctx = getattr(request.app.state, "ctx", None)
    file_store = getattr(request.app.state, "file_store", None)
    run_input = await command_endpoints.prepare_run_from_messages(
        [{"role": "user", "content": objective}],
        file_store,
    )
    run_port = getattr(request.app.state, "run_port", None)
    agent_raw = (
        {"id": coordinator_agent_id, "name": coordinator_agent_id}
        if coordinator_agent_id
        else None
    )
    agent = command_endpoints.parse_agent_ref(agent_raw)
    run_request = command_endpoints.RunRequest(
        profile="web-assistant",
        question=run_input.question,
        user_text=run_input.user_text,
        mode=command_endpoints.resolve_profile_mode(ctx, mode),
        attachment_ids=run_input.attachment_ids,
        prior_turns=run_input.prior_turns,
        agent=agent,
        device_id="",
        plane="",
        extra_plane="",
        execution_target="",
        options={
            "room_id": room_id,
            "correlation_id": correlation_id,
            "selected_peers": list(selected_peers or ()),
        },
        ctx=ctx,
    )
    receipt = await run_port.create_and_dispatch(run_request)
    if receipt.accepted:
        await register_gateway_run(
            request,
            run_id=receipt.run_id,
            topic_id=room_id,
            agent_id=str(agent.agent_id),
            body={"messages": [{"role": "user", "content": objective}], "scope": "main"},
        )
    return RunDispatchResult(
        run_id=receipt.run_id,
        trace_id=receipt.trace_id,
        accepted=receipt.accepted,
        rejection_reason=receipt.rejection_reason,
    )


async def _read_run_status(request: Request, run_id: str) -> RunOutcome:
    """Read a room-dispatched run's terminal outcome via ``RunPort.summary``."""
    run_port = getattr(request.app.state, "run_port", None)
    if run_port is None:
        return RunOutcome(status="unknown", error="run_port unavailable")
    summary = await run_port.summary(run_id)
    if summary is None:
        return RunOutcome(status="unknown", error="run not found")
    return RunOutcome(
        status=str(summary.get("status") or summary.get("session_status") or "unknown"),
        error=str(summary.get("error") or ""),
        output=str(summary.get("output") or ""),
    )


def _dispatcher_for(request: Request, room_id: str) -> RoomDispatcher:
    """Build a RoomDispatcher wired to the live RunPort for this request."""
    return RoomDispatcher(
        room_repository=JsonRoomRepository(),
        message_store=JsonRoomMessageStore(),
        run_starter=lambda *, objective, mode, correlation_id, coordinator_agent_id=None, selected_peers=None, room_id=room_id: _start_run(
            request,
            room_id=room_id,
            objective=objective,
            mode=mode,
            correlation_id=correlation_id,
            coordinator_agent_id=coordinator_agent_id,
            selected_peers=selected_peers,
        ),
        run_status_reader=lambda run_id: _read_run_status(request, run_id),
    )


async def create_room(request: Request) -> JSONResponse:
    """``POST /v1/rooms`` —— 创建房间。"""
    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error("invalid JSON body", status_code=400, code="invalid_json")
    if not isinstance(body, dict):
        return _error("body must be a JSON object", status_code=400, code="invalid_request")

    try:
        room = RoomSpec.model_validate(body)
    except ValidationError as exc:
        return _error(f"invalid room spec: {exc}", status_code=400, code="invalid_room_spec")

    JsonRoomRepository().save(room)
    return _json(room.model_dump(), status_code=201)


async def list_rooms(request: Request) -> JSONResponse:
    """``GET /v1/rooms`` —— 列出所有房间。"""
    rooms = JsonRoomRepository().list_rooms()
    return _json({"rooms": [room.model_dump() for room in rooms]})


async def get_room(request: Request) -> JSONResponse:
    """``GET /v1/rooms/{room_id}`` —— 获取单个房间。"""
    room_id = str(request.path_params.get("room_id") or "")
    room = JsonRoomRepository().get(room_id)
    if room is None:
        return _error(f"room not found: {room_id}", status_code=404, code="room_not_found")
    return _json(room.model_dump())


async def post_room_message(request: Request) -> JSONResponse:
    """``POST /v1/rooms/{room_id}/messages`` —— 发消息并触发 run 分发。"""
    room_id = str(request.path_params.get("room_id") or "")
    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error("invalid JSON body", status_code=400, code="invalid_json")
    if not isinstance(body, dict):
        return _error("body must be a JSON object", status_code=400, code="invalid_request")

    content = str(body.get("content") or "").strip()
    if not content:
        return _error("content must be a non-empty string", status_code=400, code="invalid_content")
    sender_id = str(body.get("sender_id") or "user").strip() or "user"

    run_port = getattr(request.app.state, "run_port", None)
    if run_port is None:
        return _error("run_port not available", status_code=503, code="run_port_unavailable")

    dispatcher = _dispatcher_for(request, room_id)
    try:
        started = await dispatcher.dispatch(room_id, content, sender_id=sender_id)
    except RoomNotFoundError:
        return _error(f"room not found: {room_id}", status_code=404, code="room_not_found")
    return _json(started.model_dump(), status_code=202)


async def list_room_messages(request: Request) -> JSONResponse:
    """``GET /v1/rooms/{room_id}/messages`` —— 列出房间转录。"""
    room_id = str(request.path_params.get("room_id") or "")
    dispatcher = _dispatcher_for(request, room_id)
    try:
        # Phase 2: lazy revival — append FOLDED facts for completed runs so the
        # transcript is consistent whenever it is read.
        await dispatcher.sync_completed(room_id)
    except RoomNotFoundError:
        return _error(f"room not found: {room_id}", status_code=404, code="room_not_found")
    messages = JsonRoomMessageStore().list_messages(room_id)
    return _json({"messages": [msg.model_dump() for msg in messages]})


async def rooms_root(request: Request) -> JSONResponse:
    """``/v1/rooms`` method dispatcher (POST create + GET list)."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await create_room(request)
    if method == "GET":
        return await list_rooms(request)
    return _error(f"unsupported method {method!r}", status_code=405, code="method_not_allowed")


async def room_messages_root(request: Request) -> JSONResponse:
    """``/v1/rooms/{room_id}/messages`` method dispatcher (POST + GET)."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await post_room_message(request)
    if method == "GET":
        return await list_room_messages(request)
    return _error(f"unsupported method {method!r}", status_code=405, code="method_not_allowed")


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    # Path shared by POST (create) and GET (list); rooms_root dispatches.
    RouteSpec("/v1/rooms", rooms_root, ("POST", "GET", "OPTIONS")),
    RouteSpec("/v1/rooms/{room_id}", get_room, ("GET", "OPTIONS")),
    # Path shared by POST (message) and GET (transcript); dispatcher handles both.
    RouteSpec(
        "/v1/rooms/{room_id}/messages",
        room_messages_root,
        ("POST", "GET", "OPTIONS"),
    ),
)


@plugin(
    id="lca-gateway-routes-rooms",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /v1/rooms REST routes (room runtime go-live M1).",
    test_suite="tests.collaboration.test_room_routes",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-rooms.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_rooms_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca-gateway-routes-rooms",
    )


__all__ = [
    "ROUTE_SPECS",
    "create_room",
    "get_room",
    "list_room_messages",
    "list_rooms",
    "post_room_message",
    "room_messages_root",
    "rooms_root",
    "setup",
]
