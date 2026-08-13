"""Starlette composition root: routes and injected singletons. No business."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute

from gateway.console.api import create_session as create_console_session
from gateway.console.attach import attach_session
from gateway.console.sessions import ConsoleBook
from gateway.cors import CORS_HEADERS
from gateway.files import download_file, get_file_meta
from gateway.host_sandbox import HostSandbox
from gateway.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.presence.api import list_devices
from gateway.presence.registry import PresenceRegistry
from gateway.presence.rpc import ExecHub
from gateway.presence.settings import PresenceSettings
from gateway.presence.ws import connect_host
from gateway.runs.api import (
    answer_run,
    cancel_run,
    create_run,
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
from lca.layer0_infra.sandbox.factory import set_sandbox_resolver

_registry = RunRegistry()
_file_store = get_default_file_store()
_presence = PresenceRegistry()
_consoles = ConsoleBook()
_presence_settings = PresenceSettings()
_exec_hub = ExecHub()


def get_registry() -> RunRegistry:
    return _registry


def get_file_store() -> LocalFileStore:
    return _file_store


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(request: Request) -> JSONResponse:
    payload = health_payload(_registry)
    payload["presence"] = request.app.state.presence.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, _file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, _file_store)


def create_app(
    registry: RunRegistry | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
    presence: PresenceRegistry | None = None,
    consoles: ConsoleBook | None = None,
    presence_settings: PresenceSettings | None = None,
) -> Starlette:
    """Factory: tests inject RunRegistry / LLMResolver / FileStore / Presence."""
    global _registry, _file_store, _presence, _consoles, _presence_settings, _exec_hub
    if registry is not None:
        _registry = registry
    if file_store is not None:
        _file_store = file_store
        set_default_file_store(file_store)
    if presence is not None:
        _presence = presence
    if consoles is not None:
        _consoles = consoles
    if presence_settings is not None:
        _presence_settings = presence_settings
    set_sandbox_resolver(lambda: HostSandbox.from_presence(_presence, _exec_hub))
    if llm_resolver is not None:
        set_llm_resolver(llm_resolver)
    else:
        set_llm_resolver(ProductionLLMResolver())
    application = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
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
            Route("/presence/devices", list_devices, methods=["GET", "OPTIONS"]),
            Route("/console/sessions", create_console_session, methods=["POST", "OPTIONS"]),
            WebSocketRoute("/presence/connect", connect_host),
            WebSocketRoute("/console/sessions/{session_id}", attach_session),
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
        ],
    )
    application.state.registry = _registry
    application.state.file_store = _file_store
    application.state.presence = _presence
    application.state.consoles = _consoles
    application.state.host_token = _presence_settings.token
    application.state.host_subject = _presence_settings.subject
    application.state.exec_hub = _exec_hub
    return application


app = create_app()
