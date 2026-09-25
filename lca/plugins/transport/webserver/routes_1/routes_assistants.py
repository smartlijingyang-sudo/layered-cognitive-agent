"""Register ``/v1/assistants`` REST surface (ADR-0187 §3 D7 + PR-5).

Declarative :class:`RouteSpec` catalog with nine endpoints that mirror the
``AssistantCatalog`` / ``AssistantSkillOverlay`` / ``AssistantJobs``
protocols (PR-2 / PR-8). Handler bodies intentionally short-circuit with
HTTP 501 + ``COMPAT`` markers until the owning plugin lands and the
capability is populated by a real implementation.

Capability contract:

- ``route_registry`` —— required; registration aborts when absent.
- ``assistant.catalog`` / ``assistant.skill_overlay`` / ``assistant.jobs``
  —— **not** declared as plugin ``requires``; instead each handler consults
  ``request.app.state.assistant_catalog`` / ``assistant_skill_overlay`` /
  ``assistant_jobs`` and falls back to the 501 envelope when absent. This
  keeps the routes mountable on profiles without the assistant plugins
  (web-standard today) while preserving fail-closed semantics once they land.

Routes:

- ``POST /v1/assistants`` …… ``catalog.create``
- ``GET  /v1/assistants`` …… ``catalog.list``
- ``GET  /v1/assistants/{assistant_id}`` …… ``catalog.get``
- ``PATCH /v1/assistants/{assistant_id}/profile`` …… ``catalog.revise_profile``
- ``POST /v1/assistants/{assistant_id}/skills:install`` …… ``overlay.install``
  (PR-6 wired: 503 when overlay absent, 4xx on rejection, 200 + receipt)
- ``POST /v1/assistants/{assistant_id}/retire`` …… ``catalog.retire``
- ``GET  /v1/assistants/{assistant_id}/jobs`` …… ``jobs.list_jobs``
- ``POST /v1/assistants/{assistant_id}/jobs`` …… ``jobs.register``
- ``POST /v1/assistants/{assistant_id}/jobs/{job_id}:fire`` …… ``jobs.fire``

The catalog handler bodies return a stable JSON envelope with status code
501 and a ``code="catalog_unavailable"`` field whenever the catalog is
missing. Both honour ADR-0187 §3 D7 "fail-closed 4xx, no silent fallback
to default agent".
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import ProfilePatch

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_JOBS,
    ASSISTANT_SKILL_OVERLAY,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.assistant.ownership import UserAssistantBinding
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.memory.operational_skills import SkillImportError
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
    AssistantDigestMismatch,
)
from lca.plugins.transport.webserver.handlers.auth.user import (
    auth_config_of,
    user_id_from_request,
)
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route.register import register_routes

_ASSISTANT_NOT_IMPLEMENTED_MARKER = (
    "COMPAT(delete-when: assistant.catalog plugin present in resolved profile; "
    "tracking: ADR-0187 PR-3)"
)

_ASSISTANT_JOBS_MARKER = (
    "COMPAT(delete-when: 2026-12-31, scope: assistant.jobs capability 接入 "
    "app.state.assistant_jobs 后补真实 handler body)"
)


def _json(payload: dict[str, Any], *, status_code: int) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _not_implemented(code: str, detail: str = "") -> JSONResponse:
    """Return the stable 501 envelope used while PR-3 catalog lands.

    Handler bodies in this module call this helper until the
    ``assistant.catalog`` capability is bound to a real implementation;
    the marker documents the delete-when condition.
    """
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "type": "not_implemented",
            "marker": _ASSISTANT_NOT_IMPLEMENTED_MARKER,
        }
    }
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=501)


def _catalog_from_request(request: Request) -> Any | None:
    """Return the live catalog handle from ``app.state``, else ``None``.

    The catalog plugin (PR-3) installs ``request.app.state.assistant_catalog``;
    until then this returns ``None`` and the handler short-circuits to 501.
    """
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_catalog", None)


def _skill_overlay_from_request(request: Request) -> Any | None:
    """Return the skill-overlay handle from ``app.state``, else ``None``.

    ``assistant.skill_overlay`` 由 ``lca.plugins.assistant.skill_overlay``
    (PR-6) provide;未挂助理 bundle 的 profile 取不到 ⇒ handler 回 503。
    """
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_skill_overlay", None)


def _jobs_from_request(request: Request) -> Any | None:
    """Return the assistant-jobs handle from ``app.state`` (PR-8)."""
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_jobs", None)


def _jobs_not_implemented(code: str, detail: str = "") -> JSONResponse:
    """Return the stable 501 envelope for jobs routes until the jobs
    capability is wired to ``app.state.assistant_jobs``."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "type": "not_implemented",
            "marker": _ASSISTANT_JOBS_MARKER,
        }
    }
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=501)


def _error_envelope(
    code: str,
    *,
    status_code: int,
    error_type: str,
    detail: str = "",
) -> JSONResponse:
    """Stable error envelope for the wired assistant handlers (PR-6)."""
    payload: dict[str, Any] = {"error": {"code": code, "type": error_type}}
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=status_code)


def _user_from_request(request: Request) -> tuple[str, JSONResponse | None]:
    """解析请求身份（ADR-0252 D4）；返回 ``(user_id, error_response)``。"""
    expected_token, dev_mode = auth_config_of(request)
    return user_id_from_request(request, expected_token=expected_token, dev_mode=dev_mode)


def _ownership_from_request(request: Request) -> Any | None:
    """读 ``app.state.assistant_ownership``；未装配返回 ``None``。"""
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_ownership", None)


def _is_dev_mode(request: Request) -> bool:
    _, dev_mode = auth_config_of(request)
    return dev_mode


def _ownership_error(request: Request, user_id: str, assistant_id: str) -> JSONResponse | None:
    """归属校验（ADR-0252 D6）：非 owner 一律 404（不泄露存在性）。

    ``dev_mode`` 或 ownership 未装配时放行（存量单用户行为不变）。
    """
    if _is_dev_mode(request):
        return None
    ownership = _ownership_from_request(request)
    if ownership is None:
        return None
    owner = ownership.owner_of(assistant_id)
    if owner is None or owner != user_id:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail="assistant 不存在",
        )
    return None


def _bind_ownership(
    request: Request,
    *,
    user_id: str,
    assistant_id: str,
    client_id: str,
    role_id: str | None,
    initial_skills: tuple[str, ...],
) -> None:
    """创建后写入归属关系（ADR-0252 D3）；ownership 未装配时静默跳过。"""
    ownership = _ownership_from_request(request)
    if ownership is None:
        return
    ownership.ensure_user(user_id)
    ownership.bind(
        UserAssistantBinding(
            user_id=user_id,
            assistant_id=assistant_id,
            client_id=client_id or assistant_id,
            role_id=role_id,
            initial_skills=initial_skills,
        )
    )


def _parse_skill_source(raw: Any) -> SkillSource | None:
    """body ``source`` → :class:`SkillSource`;不支持的形状返回 ``None``。

    支持:``{"url": ...}`` / ``{"local_path": ...}`` 对象,或裸字符串
    (``http(s)://`` 前缀 ⇒ url;绝对路径 ⇒ local_path)。
    """
    if isinstance(raw, dict):
        try:
            return SkillSource(
                url=str(raw.get("url") or ""),
                local_path=str(raw.get("local_path") or ""),
            )
        except ValueError:
            return None
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        try:
            if text.startswith(("http://", "https://")):
                return SkillSource(url=text)
            return SkillSource(local_path=text)
        except ValueError:
            return None
    return None


async def create_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants`` —— ``AssistantCatalog.create`` entry。

    状态码契约（ADR-0187 §3 D7 fail-closed + ADR-0252 D4/D6）：

    - catalog capability 不在场 ⇒ 501 ``catalog_unavailable``；
    - 身份不可解析 ⇒ 401（``dev_mode`` 外）；
    - body 非法 / name 缺失 / 未知 template ⇒ 400；
    - 成功 ⇒ 201 + handle + profile 视图，并写入归属关系。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.create")

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="name 必须为非空字符串",
        )
    description = body.get("description") or ""
    template_id = body.get("template_id") or "assistant.default"
    seed_user_md = body.get("seed_user_md") or None
    from_role = body.get("from_role") or None
    client_id = body.get("client_id") or ""
    initial_skills_raw = body.get("initial_skills") or []
    if not isinstance(description, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="description 必须为字符串",
        )
    if not isinstance(template_id, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="template_id 必须为字符串",
        )
    if from_role is not None and not isinstance(from_role, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="from_role 必须为字符串",
        )
    if seed_user_md is not None and not isinstance(seed_user_md, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="seed_user_md 必须为字符串",
        )
    if not isinstance(client_id, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="client_id 必须为字符串",
        )
    if not isinstance(initial_skills_raw, list) or not all(
        isinstance(skill, str) for skill in initial_skills_raw
    ):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="initial_skills 必须为字符串数组",
        )
    initial_skills = tuple(dict.fromkeys(initial_skills_raw))

    try:
        handle = catalog.create(
            CreateAssistantRequest(
                name=name.strip(),
                description=description.strip(),
                template_id=template_id,
                seed_user_md=seed_user_md,
                from_role=from_role.strip()
                if isinstance(from_role, str) and from_role.strip()
                else None,
                initial_skills=initial_skills,
                owner_user_id=user_id,
            )
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )

    _bind_ownership(
        request,
        user_id=user_id,
        assistant_id=handle.assistant_id,
        client_id=client_id,
        role_id=from_role.strip() if isinstance(from_role, str) and from_role.strip() else None,
        initial_skills=initial_skills,
    )

    return _json(
        {
            "assistant_id": handle.assistant_id,
            "home_path": handle.home_path,
            "revision_seq": handle.revision_seq,
            "template_id": template_id,
            "profile": _profile_view(handle.home_path),
        },
        status_code=201,
    )


def _profile_view(home_path: str) -> dict[str, Any]:
    """Read ``profile.json`` next to the created Home for the 201 response.

    Failure: unreadable/invalid profile.json → empty view (creation already
    succeeded; the response stays 201 with a degraded profile block).
    """
    import json
    from pathlib import Path

    try:
        raw = json.loads((Path(home_path) / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


async def list_assistants(request: Request) -> JSONResponse:
    """``GET /v1/assistants`` —— ``AssistantCatalog.list``（ADR-0252 D6 归属隔离）。

    ``dev_mode`` 保持存量行为（列出全部）；非 dev 模式只返回调用者拥有的
    Home（``manifest.user_id`` 过滤）。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.list")
    items = catalog.list() if _is_dev_mode(request) else catalog.list(user_id=user_id)
    summaries = [
        {
            "assistant_id": item.assistant_id,
            "name": item.name,
            "status": item.status,
            "template_id": item.template_id,
            "revision_seq": item.revision_seq,
            "home_path": item.home_path,
            "skill_count": item.skill_count,
            "job_count": item.job_count,
            "updated_at": item.updated_at,
        }
        for item in items
    ]
    return _json({"assistants": summaries}, status_code=200)


async def assistants_root(request: Request) -> JSONResponse:
    """``/v1/assistants`` method dispatcher (POST + GET share the path)."""
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await create_assistant(request)
    if method == "GET":
        return await list_assistants(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _not_implemented("catalog_unavailable", f"unsupported method {method!r}")


async def get_assistant(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}`` —— ``AssistantCatalog.get``.

    Response projects the serializable ``AssistantSpec`` fields only;
    ``agent_spec`` carries a live LLM adapter and never leaves the process.

    状态码契约（ADR-0252 D6）：身份不可解析 ⇒ 401；未知 id ⇒ 404；
    digest 不匹配 ⇒ 409（fail-closed，唯一恢复路径 = reimport）；
    非 owner ⇒ 404（不泄露存在性）。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.get")
    assistant_id = str(request.path_params.get("assistant_id") or "")

    try:
        spec = catalog.get(assistant_id)
    except AssistantDigestMismatch as exc:
        return _error_envelope(
            "digest_mismatch", status_code=409, error_type="conflict", detail=str(exc)
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    return _json(
        {
            "assistant_id": spec.assistant_id,
            "home_path": spec.home_path,
            "revision_seq": spec.revision_seq,
            "template_id": spec.template_id,
            "profile_name": spec.profile_name,
            "profile_description": spec.profile_description,
            "bootstrap": {
                "soul_digest": spec.bootstrap.soul_digest,
                "user_digest": spec.bootstrap.user_digest,
                "agents_digest": spec.bootstrap.agents_digest,
            },
            "skill_ids": list(spec.skill_ids),
            "job_ids": list(spec.job_ids),
            "grant_digest": spec.grant_digest,
            "tools_policy_digest": spec.tools_policy_digest,
        },
        status_code=200,
    )


_PROFILE_PATCH_FIELDS = (
    "profile_name",
    "profile_description",
    "profile_opening_message",
    "profile_locale",
    "profile_model",
    "profile_runtime",
    "soul_md",
    "user_md",
    "agents_md",
    "goals_yaml",
    "grants_yaml",
    "tools_yaml",
    "plan_yaml",
)


def _profile_patch_from_body(body: dict[str, Any]) -> ProfilePatch:
    """把 PATCH body 映射为 ``ProfilePatch``（ADR-0242 D9/D10 字段）。

    ``None`` 表示「不动」；空字符串表示「清空字段」（语义由 Catalog 决定）。
    未知字段 / 类型错误抛 ``ValueError``（路由映射 400）。
    """
    from lca.contracts.protocols.assistant.catalog import ProfilePatch

    unknown = set(body) - set(_PROFILE_PATCH_FIELDS) - {"actor"}
    if unknown:
        raise ValueError(f"未知字段: {', '.join(sorted(unknown))}")

    def _opt_str(key: str) -> str | None:
        value = body.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{key} 必须为字符串或 null")
        return value

    runtime = body.get("profile_runtime")
    if runtime is not None and not isinstance(runtime, dict):
        raise ValueError("profile_runtime 必须为 object 或 null")

    return ProfilePatch(
        profile_name=_opt_str("profile_name"),
        profile_description=_opt_str("profile_description"),
        profile_opening_message=_opt_str("profile_opening_message"),
        profile_locale=_opt_str("profile_locale"),
        profile_model=_opt_str("profile_model"),
        profile_runtime=dict(runtime) if isinstance(runtime, dict) else None,
        soul_md=_opt_str("soul_md"),
        user_md=_opt_str("user_md"),
        agents_md=_opt_str("agents_md"),
        goals_yaml=_opt_str("goals_yaml"),
        grants_yaml=_opt_str("grants_yaml"),
        tools_yaml=_opt_str("tools_yaml"),
        plan_yaml=_opt_str("plan_yaml"),
    )


async def revise_assistant_profile(request: Request) -> JSONResponse:
    """``PATCH /v1/assistants/{assistant_id}/profile`` —— ``catalog.revise_profile``.

    状态码契约（ADR-0187 §3 D7 fail-closed + ADR-0252 D6）：

    - 身份不可解析 ⇒ 401；
    - catalog capability 不在场 ⇒ 501 ``catalog_unavailable``；
    - body 非法 / 未知字段 / patch 类型错误 ⇒ 400；
    - 未知 assistant ⇒ 404；配置面 digest 不匹配 ⇒ 409；非 owner ⇒ 404；
    - 成功 ⇒ 200 + ``PlanRevision`` 字段 + 更新后的 profile 视图。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.revise_profile")
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    actor_raw = body.get("actor")
    if actor_raw is not None and not isinstance(actor_raw, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="actor 必须为字符串",
        )
    actor = actor_raw.strip() if actor_raw else "system"

    try:
        patch = _profile_patch_from_body(body)
    except ValueError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )

    try:
        revision = catalog.revise_profile(assistant_id, patch, actor=actor)
        home_path = catalog.get(assistant_id).home_path
    except AssistantDigestMismatch as exc:
        return _error_envelope(
            "digest_mismatch",
            status_code=409,
            error_type="conflict",
            detail=str(exc),
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail=str(exc),
        )
    except ValueError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )

    return _json(
        {
            "assistant_id": revision.assistant_id,
            "revision_seq": revision.revision_seq,
            "manifest_digest": revision.manifest_digest,
            "actor": revision.actor,
            "snapshot_path": revision.snapshot_path,
            "revised_at": revision.revised_at,
            "profile": _profile_view(home_path),
        },
        status_code=200,
    )


async def install_assistant_skill(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/skills:install`` —— ``overlay.install`` (PR-6).

    状态码契约(ADR-0187 §3 D7 fail-closed + ADR-0252 D6):

    - 身份不可解析 ⇒ 401；
    - overlay capability 不在场 ⇒ 503 ``skill_overlay_unavailable``;
    - body 非法 / source 形状不支持 ⇒ 400;
    - 助理不存在 ⇒ 404;配置面 digest 不匹配 ⇒ 409;非 owner ⇒ 404;
    - 拉取 / 格式 / 0067 三闸拒收 ⇒ 422 ``install_rejected``;
    - 成功 ⇒ 200 + ``SkillInstallReceipt``(含四件套字段)。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    overlay = _skill_overlay_from_request(request)
    if overlay is None:
        return _error_envelope(
            "skill_overlay_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.skill_overlay capability 不在已解析 profile 中",
        )
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )
    source = _parse_skill_source(body.get("source"))
    if source is None:
        return _error_envelope(
            "invalid_source",
            status_code=400,
            error_type="invalid_request",
            detail="source 必须为 {'url': ...} / {'local_path': ...} 或等价裸字符串",
        )
    actor = str(body.get("actor") or "").strip() or "system"
    try:
        receipt = await overlay.install(assistant_id, source, actor=actor)
    except AssistantDigestMismatch as exc:
        return _error_envelope(
            "digest_mismatch",
            status_code=409,
            error_type="conflict",
            detail=str(exc),
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail=str(exc),
        )
    except SkillImportError as exc:
        return _error_envelope(
            "install_rejected",
            status_code=422,
            error_type="validation_failed",
            detail=str(exc),
        )
    except ValueError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )
    return _json({"receipt": dataclasses.asdict(receipt)}, status_code=200)


async def import_lobehub_agent(request: Request) -> JSONResponse:
    """``POST /v1/assistants/import-lobehub`` — 从 LobeHub agent JSON 导入助理。

    LobeHub agent JSON 形态：
    ``{title, description, avatar, systemRole, plugins?, openingMessage?}``

    映射规则：
    - title → name
    - description → description
    - avatar → emoji（取第一个字符如果是 emoji，否则用默认 🤖）
    - systemRole → SOUL.md 全文

    201 + assistant handle on success。
    """
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "import_lobehub")

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    name = body.get("title") or body.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="title/name 必须为非空字符串",
        )
    description = str(body.get("description") or "").strip()
    system_role = str(body.get("systemRole") or body.get("system_role") or "").strip()
    avatar = str(body.get("avatar") or "").strip()

    emoji = _extract_emoji(avatar)

    from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

    try:
        handle = catalog.create(
            CreateAssistantRequest(
                name=name.strip(),
                description=description,
                template_id="assistant.default",
                seed_user_md=None,
            )
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )

    from pathlib import Path

    home = Path(handle.home_path)

    if system_role:
        (home / "SOUL.md").write_text(system_role, encoding="utf-8")

    if emoji:
        import json

        profile_path = home / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["emoji"] = emoji
        profile["source"] = "lobehub"
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    from lca.plugins.assistant.home._home_layout import (
        build_manifest,
        load_manifest,
        write_manifest,
    )

    manifest = load_manifest(home, handle.assistant_id)
    new_manifest = build_manifest(
        assistant_id=handle.assistant_id,
        template_id="assistant.default",
        revision_seq=int(manifest.get("revision_seq", 0)) + (1 if system_role or emoji else 0),
        home=home,
    )
    if system_role or emoji:
        new_manifest["source"] = "lobehub"
        write_manifest(home, new_manifest)

    return _json(
        {
            "assistant_id": handle.assistant_id,
            "home_path": handle.home_path,
            "revision_seq": handle.revision_seq,
            "source": "lobehub",
            "profile": _profile_view(handle.home_path),
        },
        status_code=201,
    )


def _extract_emoji(avatar: str) -> str:
    """从 LobeHub avatar 字段提取 emoji。

    LobeHub avatar 可以是 emoji 字符或 URL。如果是 emoji 则返回，
    否则返回空字符串（让 catalog 用默认 emoji）。
    """
    if not avatar:
        return ""
    if avatar.startswith(("http://", "https://", "/")):
        return ""
    if len(avatar) <= 4:
        return avatar
    return ""


async def bind_agent(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/bind-agent`` —— owner 回填 LobeHub agent 行。

    ADR-0252 D8：浏览器 onboarding 路径在 LCA 创建 Home 后调原生
    ``agent.createAgent`` 生成 ``agt_*``，再把 ``agent_id`` 回填到归属记录。
    幂等：已绑定同一 ``agent_id`` 返回 200；未知/非 owner ⇒ 404。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership = _ownership_from_request(request)
    if ownership is None:
        return _error_envelope(
            "ownership_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.ownership capability 不在已解析 profile 中",
        )
    owner = ownership.owner_of(assistant_id)
    if owner is None or owner != user_id:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail="assistant 不存在",
        )

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )
    agent_id = str(body.get("agent_id") or "").strip()
    if not agent_id:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="agent_id 必须为非空字符串",
        )

    ownership.set_agent_id(assistant_id, agent_id)
    return _json({"assistant_id": assistant_id, "agent_id": agent_id}, status_code=200)


async def register_lobehub(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/register-lobehub`` —— bridge 注册重试。

    ADR-0252 D8：浏览器路径用原生 ``agent.createAgent`` + ``bind-agent``；
    本端点是 LCA bridge 路径（dev/CLI/skill 创建）的失败重试。owner-only，
    已绑定 ``agent_id`` 时 no-op 返回现有值；bridge 未装配/注册失败 502。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership = _ownership_from_request(request)
    if ownership is None:
        return _error_envelope(
            "ownership_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.ownership capability 不在已解析 profile 中",
        )
    owner = ownership.owner_of(assistant_id)
    if owner is None or owner != user_id:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail="assistant 不存在",
        )

    existing = ownership.agent_id_of(assistant_id)
    if existing:
        return _json({"assistant_id": assistant_id, "agent_id": existing}, status_code=200)

    bridge = getattr(request.app.state, "assistant_frontend_bridge", None)
    if bridge is None or not getattr(bridge, "enabled", False):
        return _error_envelope(
            "bridge_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.frontend_bridge 未装配或未启用",
        )

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.get")
    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail=str(exc),
        )

    import json
    from pathlib import Path

    home = Path(spec.home_path)
    profile: dict[str, object] = {}
    try:
        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        profile = {}
    emoji = str(profile.get("emoji") or "🤖")
    opening_message = str(profile.get("opening_message") or "")
    soul = ""
    try:
        soul = (home / "SOUL.md").read_text(encoding="utf-8")
    except OSError:
        soul = ""

    agent_id = await bridge.register(
        assistant_id=assistant_id,
        name=spec.profile_name,
        description=spec.profile_description,
        emoji=emoji,
        system_role=soul,
        opening_message=opening_message,
        client_id=f"lca-{assistant_id}",
    )
    if agent_id is None:
        return _error_envelope(
            "bridge_registration_failed",
            status_code=502,
            error_type="bad_gateway",
            detail="LobeHub agent 行注册失败，可稍后重试",
        )
    ownership.set_agent_id(assistant_id, agent_id)
    return _json({"assistant_id": assistant_id, "agent_id": agent_id}, status_code=200)


async def retire_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/retire`` —— ``catalog.retire``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.retire")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def list_assistant_jobs(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/jobs`` —— ``AssistantJobs.list_jobs``."""
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.list_jobs")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")


async def create_assistant_job(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/jobs`` —— ``AssistantJobs.register``."""
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.register")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")


async def assistant_jobs_root(request: Request) -> JSONResponse:
    """``/v1/assistants/{assistant_id}/jobs`` method dispatcher (GET + POST)."""
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await create_assistant_job(request)
    if method == "GET":
        return await list_assistant_jobs(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _jobs_not_implemented("jobs_unavailable", f"unsupported method {method!r}")


async def fire_assistant_job(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/jobs/{job_id}:fire`` —— ``jobs.fire``.

    Phase 1 仅人工投递（``actor="manual"`` Trigger → 0093 WorkQueue）。
    """
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.fire")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    # Path is shared between POST (create) and GET (list); the
    # :func:`assistants_root` dispatcher handles both methods.
    RouteSpec(
        "/v1/assistants",
        assistants_root,
        ("POST", "GET", "OPTIONS"),
    ),
    # import-lobehub must come before {assistant_id} to avoid path conflict
    RouteSpec(
        "/v1/assistants/import-lobehub",
        import_lobehub_agent,
        ("POST", "OPTIONS"),
    ),
    RouteSpec("/v1/assistants/{assistant_id}", get_assistant, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/assistants/{assistant_id}/profile",
        revise_assistant_profile,
        ("PATCH", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/skills:install",
        install_assistant_skill,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/bind-agent",
        bind_agent,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/register-lobehub",
        register_lobehub,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/retire",
        retire_assistant,
        ("POST", "OPTIONS"),
    ),
    # Path is shared between POST (register) and GET (list); the
    # :func:`assistant_jobs_root` dispatcher handles both methods.
    RouteSpec(
        "/v1/assistants/{assistant_id}/jobs",
        assistant_jobs_root,
        ("POST", "GET", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/jobs/{job_id}:fire",
        fire_assistant_job,
        ("POST", "OPTIONS"),
    ),
)


@plugin(
    id="lca.plugins.transport.webserver.routes_1.routes_assistants",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=("Register /v1/assistants CRUD REST surface (ADR-0187 §3 D7 + PR-5). "),
    test_suite="tests.lca_plugins.transport.webserver.test_routes_assistants",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca.plugins.transport.webserver.routes_assistants.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "route_registry",
            ASSISTANT_CATALOG.key,
            ASSISTANT_SKILL_OVERLAY.key,
            ASSISTANT_JOBS.key,
        ),
        emits=("assistant_routes.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Mount the nine ``/v1/assistants`` routes.

    The routes always mount (``route_registry`` is the only required cap).
    Catalog / overlay / jobs lookups happen inside each handler via
    :func:`_catalog_from_request` / :func:`_jobs_from_request` so the plugin
    stays mountable on profiles without the assistant plugins
    (e.g. ``web-standard``).
    """
    del config
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca.plugins.transport.webserver.routes_1.routes_assistants",
    )


__all__ = [
    "ROUTE_SPECS",
    "assistant_jobs_root",
    "assistants_root",
    "create_assistant",
    "create_assistant_job",
    "fire_assistant_job",
    "get_assistant",
    "import_lobehub_agent",
    "install_assistant_skill",
    "list_assistant_jobs",
    "list_assistants",
    "retire_assistant",
    "revise_assistant_profile",
    "setup",
]
