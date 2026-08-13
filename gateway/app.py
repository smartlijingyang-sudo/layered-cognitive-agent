"""Starlette composition root: routes and injected singletons. No business."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gateway.cors import CORS_HEADERS
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


def get_registry() -> RunRegistry:
    return _registry


def get_file_store() -> LocalFileStore:
    return _file_store


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse(health_payload(_registry), headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, _file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, _file_store)


def create_app(
    registry: RunRegistry | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
) -> Starlette:
    """Factory: tests inject RunRegistry / LLMResolver / FileStore."""
    global _registry, _file_store
    if registry is not None:
        _registry = registry
    if file_store is not None:
        _file_store = file_store
        set_default_file_store(file_store)
    if llm_resolver is not None:
        set_llm_resolver(llm_resolver)
    else:
        set_llm_resolver(ProductionLLMResolver())
    return Starlette(
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
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
        ],
    )


app = create_app()
