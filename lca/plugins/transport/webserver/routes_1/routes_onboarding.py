"""Register ``/v1/onboarding/presets`` —— Onboarding 预设（ADR-0252 D7）。

返回角色预设（``roles/`` 角色卡）与技能目录（``~/.lca/skills`` 全局技能库），
供前端 ``AgentPickerStep`` / ``SkillCapabilityStep`` 消费：

- ``roles`` —— id/title/description/avatar/category（department 映射分类）；
- ``skills`` —— id/name/description（含 ``SKILL.md`` + ``manifest.json``
  的可物化包，与 catalog 默认物化全集一致）。

身份：``dev_mode`` 下缺头回落 ``local-dev-user``；非 dev 模式缺身份 401。
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.plugins.transport.webserver.handlers.auth.user import (
    auth_config_of,
    user_id_from_request,
)
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route.register import register_routes


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _error(detail: str, *, status_code: int, code: str) -> JSONResponse:
    return _json(
        {"error": {"code": code, "type": "invalid_request", "detail": detail}},
        status_code=status_code,
    )


def _resolver_from_request(request: Request) -> Any | None:
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "role_card_resolver", None)


async def onboarding_presets(request: Request) -> JSONResponse:
    """``GET /v1/onboarding/presets`` —— 角色预设 + 技能目录。"""
    expected_token, dev_mode = auth_config_of(request)
    user_id, auth_error = user_id_from_request(
        request, expected_token=expected_token, dev_mode=dev_mode
    )
    if auth_error is not None:
        return auth_error
    del user_id  # 预设是全局数据，不做用户过滤（ADR-0252 开放问题 3）

    roles: list[dict[str, str]] = []
    resolver = _resolver_from_request(request)
    if resolver is not None:
        for dept in resolver.list_departments():
            for entry in resolver.list_by_department(dept.department_id):
                roles.append(
                    {
                        "id": entry.role_id,
                        "title": entry.title,
                        "description": entry.summary,
                        "avatar": entry.emoji,
                        "category": entry.department,
                    }
                )

    skills: list[dict[str, str]] = []
    try:
        store = DiskSkillPackageStore()
        root = store.root
        for entry in store.list_installed():
            package_root = root / entry.skill_id
            if (package_root / "SKILL.md").is_file() and (
                package_root / "manifest.json"
            ).is_file():
                skills.append(
                    {
                        "id": entry.skill_id,
                        "name": entry.name,
                        "description": entry.summary,
                    }
                )
    except Exception:  # 全局技能库不可用时预设降级为空技能列表
        skills = []

    return _json({"roles": roles, "skills": skills}, status_code=200)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/onboarding/presets", onboarding_presets, ("GET", "OPTIONS")),
)


@plugin(
    id="lca.plugins.transport.webserver.routes_1.routes_onboarding",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /v1/onboarding/presets (ADR-0252 D7).",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca.plugins.transport.webserver.routes_onboarding.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry", "assistant.role_card_resolver"),
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
        plugin_id="lca.plugins.transport.webserver.routes_1.routes_onboarding",
    )


__all__ = ["ROUTE_SPECS", "onboarding_presets", "setup"]
