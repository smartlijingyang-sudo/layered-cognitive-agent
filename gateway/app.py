"""Starlette composition root: routes and injected singletons. No business."""

from __future__ import annotations

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
    stream_run_live,
)
from gateway.runs.execute import set_llm_resolver
from gateway.runs.session import RunRegistry
from lca.layer0_infra.file_store import (
    LocalFileStore,
    get_default_file_store,
    set_default_file_store,
)
from lca.layer0_infra.llm_resolver import LLMResolver, ProductionLLMResolver

_registry = RunRegistry()
_file_store = get_default_file_store()
_device_settings = DeviceGatewaySettings()
_devices = DeviceRegistry(_device_settings.db_path)
_device_hub = DeviceHub(_devices)


def get_registry() -> RunRegistry:
    return _registry


def get_file_store() -> LocalFileStore:
    return _file_store


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(request: Request) -> JSONResponse:
    payload = health_payload(_registry)
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, _file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, _file_store)


def create_app(
    registry: RunRegistry | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
    devices: DeviceRegistry | None = None,
) -> Starlette:
    """Factory: tests inject RunRegistry / LLMResolver / FileStore / DeviceRegistry."""
    global _registry, _file_store, _devices, _device_hub
    if registry is not None:
        _registry = registry
    if file_store is not None:
        _file_store = file_store
        set_default_file_store(file_store)
    if devices is not None:
        _devices = devices
        _device_hub = DeviceHub(devices)
    bind_devices(_devices, _device_hub)
    if llm_resolver is not None:
        set_llm_resolver(llm_resolver)
    else:
        set_llm_resolver(ProductionLLMResolver())
    application = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/context", get_context, methods=["GET", "OPTIONS"]),
            Route("/runs", create_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
            Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
            Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
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
        ],
    )
    application.state.registry = _registry
    application.state.file_store = _file_store
    application.state.devices = _devices
    application.state.device_hub = _device_hub
    application.state.device_settings = _device_settings
    return application


app = create_app()
