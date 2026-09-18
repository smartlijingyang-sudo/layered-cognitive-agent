"""Register ``/v1/role-cards`` REST surface —— 角色档案浏览 API。

四个端点：

- ``GET /v1/role-cards`` …… 列部门摘要（department_id / label / count）
- ``GET /v1/role-cards/departments/{department_id}`` …… 列部门下角色索引
- ``GET /v1/role-cards/{role_id}`` …… 取完整角色卡片（含 backstory 全文）
- ``GET /v1/role-cards/search?q=<keyword>`` …… 按关键词搜索

Capability contract：

- ``route_registry`` —— 必须；
- ``assistant.role_resolver`` —— 不声明为 plugin requires；handler 经
  ``request.app.state.role_card_resolver`` 取，缺位返回 503。

role_id 中的 ``/`` 在 path param 里需要 URL encode（Starlette 支持 path
参数含 ``/`` 当用 ``{role_id:path}``）。
"""

from __future__ import annotations

import dataclasses
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.assistant.role_resolver import (
    RoleNotFoundError,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route.register import register_routes


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _resolver_from_request(request: Request) -> Any | None:
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "role_card_resolver", None)


async def list_role_card_departments(request: Request) -> JSONResponse:
    """``GET /v1/role-cards`` — 列部门摘要。"""
    resolver = _resolver_from_request(request)
    if resolver is None:
        return _json(
            {"error": {"code": "role_resolver_unavailable", "type": "service_unavailable"}},
            status_code=503,
        )
    departments = resolver.list_departments()
    return _json(
        {
            "total_roles": sum(d.count for d in departments),
            "departments": [
                {
                    "department_id": d.department_id,
                    "label": d.label,
                    "count": d.count,
                }
                for d in departments
            ],
        }
    )


async def list_role_cards_by_department(request: Request) -> JSONResponse:
    """``GET /v1/role-cards/departments/{department_id}`` — 列部门下角色。"""
    resolver = _resolver_from_request(request)
    if resolver is None:
        return _json(
            {"error": {"code": "role_resolver_unavailable", "type": "service_unavailable"}},
            status_code=503,
        )
    department_id = str(request.path_params.get("department_id") or "")
    entries = resolver.list_by_department(department_id)
    return _json(
        {
            "department_id": department_id,
            "count": len(entries),
            "roles": [
                {
                    "role_id": e.role_id,
                    "title": e.title,
                    "summary": e.summary,
                    "emoji": e.emoji,
                }
                for e in entries
            ],
        }
    )


async def get_role_card(request: Request) -> JSONResponse:
    """``GET /v1/role-cards/{role_id:path}`` — 取完整角色卡片。"""
    resolver = _resolver_from_request(request)
    if resolver is None:
        return _json(
            {"error": {"code": "role_resolver_unavailable", "type": "service_unavailable"}},
            status_code=503,
        )
    role_id = str(request.path_params.get("role_id") or "")
    try:
        card = resolver.resolve(role_id)
    except RoleNotFoundError:
        return _json(
            {"error": {"code": "role_not_found", "type": "not_found", "detail": role_id}},
            status_code=404,
        )
    return _json(
        {
            "role_id": card.role_id,
            "title": card.title,
            "department": card.department,
            "summary": card.summary,
            "emoji": card.emoji,
            "backstory": card.backstory,
        }
    )


async def search_role_cards(request: Request) -> JSONResponse:
    """``GET /v1/role-cards/search`` — 按关键词搜索。"""
    resolver = _resolver_from_request(request)
    if resolver is None:
        return _json(
            {"error": {"code": "role_resolver_unavailable", "type": "service_unavailable"}},
            status_code=503,
        )
    query_params = getattr(request, "query_params", {})
    keyword = str(query_params.get("q") or "").strip()
    if not keyword:
        return _json(
            {"error": {"code": "missing_query", "type": "invalid_request", "detail": "q 参数必填"}},
            status_code=400,
        )
    entries = resolver.search(keyword)
    return _json(
        {
            "keyword": keyword,
            "count": len(entries),
            "roles": [
                {
                    "role_id": e.role_id,
                    "title": e.title,
                    "department": e.department,
                    "summary": e.summary,
                    "emoji": e.emoji,
                }
                for e in entries
            ],
        }
    )


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/role-cards", list_role_card_departments, ("GET", "OPTIONS")),
    RouteSpec("/v1/role-cards/search", search_role_cards, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/role-cards/departments/{department_id}",
        list_role_cards_by_department,
        ("GET", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/role-cards/{role_id:path}",
        get_role_card,
        ("GET", "OPTIONS"),
    ),
)


@plugin(
    id="lca.plugins.transport.webserver.routes_1.routes_role_cards",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /v1/role-cards REST surface for browsing the role card library.",
    test_suite="tests.lca_plugins.transport.webserver.test_routes_role_cards",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca.plugins.transport.webserver.routes_role_cards.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "route_registry",
            "assistant.role_resolver",
        ),
        emits=(),
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
        plugin_id="lca.plugins.transport.webserver.routes_1.routes_role_cards",
    )


__all__ = [
    "ROUTE_SPECS",
    "get_role_card",
    "list_role_card_departments",
    "list_role_cards_by_department",
    "search_role_cards",
    "setup",
]
