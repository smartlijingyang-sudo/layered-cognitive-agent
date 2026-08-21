"""Starlette composition root: routes and injected singletons. No business.

Boot lifecycle (ADR-0062+)
-------------------------
The harness plugin tree is booted **once** during the Starlette
lifespan startup phase, by ``lca.harness.profile.lifespan.profile_lifespan``.
This module no longer runs boot itself; it only selects which lifespan
to install.

The previous synchronous-in-an-isolated-loop workaround
(``asyncio.new_event_loop`` + ``run_until_complete``) is gone. All
async primitives created during boot now bind to the loop that
serves requests, so they survive into the request phase.

Construction order
------------------
Module-level work in this file is limited to:

  1. Importing routes and structlog config (cannot fail).
  2. Reading the ``LCA_PROFILE`` env var (pure read).

Everything that touches the filesystem or DB (``RunRegistry``,
``LocalFileStore``, ``DeviceRegistry``, ``DeviceHub``) is constructed
inside :func:`create_app`. If profile boot fails during the lifespan
startup, those objects were already constructed — but they are owned
by ``app.state``, so they are discarded with the app. No module-level
global holds a half-initialized reference.

One source of truth
-------------------
The booted plugin tree lives **once**, on ``app.state.ctx``. The
library-default holder (``lca.layer4_app.api._default_ctx_holder``)
continues to serve library callers who construct ``Agent(...)``
without going through the gateway — it is **not** written by this
boot path. Two holders, two semantics, no overlap.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute

from gateway.cors import CORS_HEADERS
from gateway.device_gateway.bind import bind_devices
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.routes import (
    agent_run as device_agent_run,
)
from gateway.device_gateway.routes import (
    connect_device,
    device_status,
)
from gateway.device_gateway.routes import (
    list_devices as list_gateway_devices,
)
from gateway.device_gateway.routes import (
    rpc as device_rpc,
)
from gateway.device_gateway.routes import (
    system_info as device_system_info,
)
from gateway.device_gateway.routes import (
    tool_call as device_tool_call,
)
from gateway.device_gateway.routes import (
    upload_files as device_upload_files,
)
from gateway.device_gateway.settings import DeviceGatewaySettings
from gateway.files import download_file, get_file_meta
from gateway.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.runs.api import (
    answer_run,
    cancel_run,
    create_run,
    get_context,
    get_run,
    get_run_doctor,
    health_payload,
    stream_journal_live,
    stream_run_live,
)
from gateway.runs.session import RunRegistry
from gateway.session_routes import (
    command_answer,
    command_cancel,
    command_inject,
    command_steer,
    create_session,
    get_snapshot,
    send_message,
    stream_events,
)
from gateway.spine import bind_session_spine, ctx_provider_from_app
from lca.harness.profile.lifespan import install_profile_lifespan
from lca.layer0_infra.file_store import (
    LocalFileStore,
    get_default_file_store,
    set_default_file_store,
)


def _configure_structlog() -> None:
    """Gateway structlog 配置：ContextVar 合并 + ISO 时间戳 + console 渲染。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


_configure_structlog()


def _build_routes() -> list[Route | WebSocketRoute]:
    return [
        Route("/health", health, methods=["GET"]),
        Route("/context", get_context, methods=["GET", "OPTIONS"]),
        Route("/journal/live", stream_journal_live, methods=["GET", "OPTIONS"]),
        Route("/runs", create_run, methods=["POST", "OPTIONS"]),
        Route("/runs/{run_id}", get_run, methods=["GET"]),
        Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
        Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
        Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
        Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions", create_session, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/messages", send_message, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/snapshot", get_snapshot, methods=["GET", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/events", stream_events, methods=["GET", "OPTIONS"]),
        Route(
            "/v1/sessions/{session_id}/commands/answer",
            command_answer,
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/v1/sessions/{session_id}/commands/cancel",
            command_cancel,
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/v1/sessions/{session_id}/commands/steer",
            command_steer,
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/v1/sessions/{session_id}/commands/inject",
            command_inject,
            methods=["POST", "OPTIONS"],
        ),
        Route("/files/{attachment_id}", _download_file, methods=["GET"]),
        Route("/files/{attachment_id}/meta", _get_file_meta, methods=["GET"]),
        Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
        Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
        Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
        Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
        Route("/api/device/status", device_status, methods=["POST", "OPTIONS"]),
        Route("/api/device/devices", list_gateway_devices, methods=["POST", "OPTIONS"]),
        Route("/api/device/tool-call", device_tool_call, methods=["POST", "OPTIONS"]),
        Route("/api/device/system-info", device_system_info, methods=["POST", "OPTIONS"]),
        Route("/api/device/rpc", device_rpc, methods=["POST", "OPTIONS"]),
        Route("/api/device/agent/run", device_agent_run, methods=["POST", "OPTIONS"]),
        Route("/api/device/files/upload", device_upload_files, methods=["POST", "OPTIONS"]),
        WebSocketRoute("/api/device/ws", connect_device),
        Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
        Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
    ]


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


def _resolve_profile_path(profile_path: str | None) -> str | None:
    """Resolve the boot profile from explicit arg, env, or local default."""
    if profile_path is not None:
        return profile_path
    env_profile = os.environ.get("LCA_PROFILE")
    if env_profile is not None:
        return env_profile
    if Path("profiles/web-standard.yaml").exists():
        return "profiles/web-standard.yaml"
    return None


# ── Routes that read from app.state.* instead of module globals ──────


async def health(request: Request) -> JSONResponse:
    registry: RunRegistry = request.app.state.registry
    payload = health_payload(registry, ctx=getattr(request.app.state, "ctx", None))
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, request.app.state.file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, request.app.state.file_store)


def get_registry() -> RunRegistry:
    """Return the active RunRegistry.

    Module-level convenience accessor for code paths that have no
    request/app handle (scripts, ops CLI). When a Starlette app is
    live, prefer ``request.app.state.registry``.

    Construction is lazy: the first call constructs the default, and
    a later ``create_app(registry=...)`` call rebinds it for tests.
    """
    global _module_registry
    if _module_registry is None:
        _module_registry = RunRegistry()
    return _module_registry


def get_file_store() -> LocalFileStore:
    """Return the active LocalFileStore (module-level fallback only).

    Construction is lazy: the first call constructs the default, and
    a later ``create_app(file_store=...)`` call rebinds it for tests.
    """
    global _module_file_store
    if _module_file_store is None:
        _module_file_store = get_default_file_store()
    return _module_file_store


# Lazy module-level singletons. Constructed on first accessor call or
# on the first ``create_app()`` invocation. Production code reads
# ``app.state.*`` instead — these globals exist only for callers that
# have no app handle. Empty until first construction.
_module_registry: RunRegistry | None = None
_module_file_store: LocalFileStore | None = None


def create_app(
    registry: RunRegistry | None = None,
    file_store: LocalFileStore | None = None,
    devices: DeviceRegistry | None = None,
    profile_path: str | None = None,
    *,
    lifespan: Any | None = None,
) -> Starlette:
    """Factory: build the Starlette app, attach infrastructure, install lifespan.

    Args:
        registry: Optional ``RunRegistry`` override (tests inject).
        file_store: Optional ``LocalFileStore`` override (tests inject).
        devices: Optional ``DeviceRegistry`` override (tests inject).
        profile_path: Path to the harness profile YAML. Boot runs in
            the lifespan if set. Falls back to ``LCA_PROFILE`` env var,
            then ``profiles/web-standard.yaml`` if it exists.
        lifespan: Pre-built Starlette lifespan. Defaults to the profile
            lifespan selected by ``profile_path``. Tests pass a custom
            lifespan to install a scripted LLM after boot.

    Returns:
        A Starlette app with ``app.state.{registry, file_store, devices,
        device_hub, device_settings}`` populated. ``app.state.ctx`` is
        set by the lifespan at startup time, not here.
    """
    global _module_registry, _module_file_store

    if registry is not None:
        _module_registry = registry
    resolved_registry = registry if registry is not None else get_registry()

    if file_store is not None:
        _module_file_store = file_store
        set_default_file_store(file_store)
    resolved_file_store = file_store if file_store is not None else get_file_store()

    device_settings = DeviceGatewaySettings()
    resolved_devices = devices if devices is not None else DeviceRegistry(device_settings.db_path)
    device_hub = DeviceHub(resolved_devices)
    bind_devices(resolved_devices, device_hub)

    resolved_profile = _resolve_profile_path(profile_path)
    if lifespan is None:
        lifespan = install_profile_lifespan(resolved_profile)

    application = Starlette(routes=_build_routes(), lifespan=lifespan)

    application.state.registry = resolved_registry
    application.state.file_store = resolved_file_store
    application.state.devices = resolved_devices
    application.state.device_hub = device_hub
    application.state.device_settings = device_settings
    application.state.profile_path = resolved_profile

    # Session spine: AgentRegistry + CommandGateway. Constructed at
    # ``create_app`` time so request handlers can resolve them, but
    # the ctx they pass to live builders is resolved lazily per call
    # via the ``ctx_provider`` below — it reads ``app.state.ctx``,
    # which is set by the lifespan after the harness profile boots.
    spine_dir = Path("traces/sessions")
    agent_registry, command_gw, _projections = bind_session_spine(
        sessions_dir=spine_dir,
        ctx_provider=ctx_provider_from_app(application),
    )
    application.state.agent_registry = agent_registry
    application.state.command_gateway = command_gw

    return application


app = create_app()
