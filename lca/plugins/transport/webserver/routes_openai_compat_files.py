"""Register OpenAI-compatible + /files routes (PR-4 + ADR-0163 决策 5).

Declarative :class:`RouteSpec` catalog. The OpenAI-compat POST routes
declare ``requires=("llm_resolver",)``; a boot that did not resolve the
LLM adapter fails fast at registration rather than at the first request.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.files import download_file, get_file_meta
from lca.plugins.transport.webserver.handlers.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from lca.plugins.transport.webserver.route_register import register_routes

_LLM_REQUIRES: tuple[str, ...] = ("llm_resolver",)


async def _download_file(request: Request) -> Response:
    return await download_file(request, request.app.state.file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, request.app.state.file_store)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/files/{attachment_id}", _download_file, ("GET",)),
    RouteSpec("/files/{attachment_id}/meta", _get_file_meta, ("GET",)),
    RouteSpec("/v1/models", list_models, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/chat/completions",
        chat_completions,
        ("POST", "OPTIONS"),
        requires=_LLM_REQUIRES,
    ),
    RouteSpec(
        "/v1/embeddings",
        embeddings_create,
        ("POST", "OPTIONS"),
        requires=_LLM_REQUIRES,
    ),
    RouteSpec(
        "/v1/responses",
        responses_create,
        ("POST", "OPTIONS"),
        requires=_LLM_REQUIRES,
    ),
)


@plugin(
    id="lca-gateway-routes-openai-compat-files",
    provides=(),
    requires=("route_registry", "llm_resolver"),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /v1/models + /v1/chat/completions + /v1/embeddings + /v1/responses + /files/{id}.",
    test_suite="tests.lca_plugins.transport.webserver.test_openai_compat_files",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-openai-compat-files.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_openai_compat_files_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca-gateway-routes-openai-compat-files",
    )
