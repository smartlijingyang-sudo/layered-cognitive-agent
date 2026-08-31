"""Register OpenAI-compatible + /files routes (PR-4 routes-openai-compat-files).

handler 内部继续复用 ``gateway.openai_shim`` / ``gateway.files`` 现有实现;
本 PR 只 plugin 化路由注册,不重构 handler 内部(留给 PR-5 清理跨层 import)。
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

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
from lca.plugins.transport.webserver.handlers.files import download_file, get_file_meta
from lca.plugins.transport.webserver.handlers.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)


async def _download_file(request: Request) -> Response:
    return await download_file(request, request.app.state.file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, request.app.state.file_store)


ROUTES: tuple[Route, ...] = (
    Route("/files/{attachment_id}", _download_file, methods=["GET"]),
    Route("/files/{attachment_id}/meta", _get_file_meta, methods=["GET"]),
    Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
    Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
    Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
    Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
)


@plugin(
    id="lca-gateway-routes-openai-compat-files",
    provides=(),
    requires=("gateway_router",),
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
        reads=("gateway_router",),
        emits=("gateway_openai_compat_files_route.registered",),
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
