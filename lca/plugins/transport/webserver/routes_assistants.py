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
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
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
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.memory.operational_skills import SkillImportError
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.assistant.catalog import (
    AssistantCatalogError,
    AssistantDigestMismatch,
)
from lca.plugins.transport.webserver.handlers.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route_register import register_routes

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
    """``POST /v1/assistants`` —— ``AssistantCatalog.create`` entry.

    状态码契约（ADR-0187 §3 D7 fail-closed）：

    - catalog capability 不在场 ⇒ 501 ``catalog_unavailable``；
    - body 非法 / name 缺失 / 未知 template ⇒ 400；
    - 成功 ⇒ 201 + handle + profile 视图。
    """
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
    if seed_user_md is not None and not isinstance(seed_user_md, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="seed_user_md 必须为字符串",
        )

    try:
        handle = catalog.create(
            CreateAssistantRequest(
                name=name.strip(),
                description=description.strip(),
                template_id=template_id,
                seed_user_md=seed_user_md,
            )
        )
    except AssistantCatalogError as exc:
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
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
    """``GET /v1/assistants`` —— ``AssistantCatalog.list``."""
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.list")
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
        for item in catalog.list()
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

    状态码契约：未知 id ⇒ 404；digest 不匹配 ⇒ 409（fail-closed，
    唯一恢复路径 = reimport）。
    """
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
                "identity_digest": spec.bootstrap.identity_digest,
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


async def revise_assistant_profile(request: Request) -> JSONResponse:
    """``PATCH /v1/assistants/{assistant_id}/profile`` —— ``catalog.revise_profile``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.revise_profile")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def install_assistant_skill(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/skills:install`` —— ``overlay.install`` (PR-6).

    状态码契约(ADR-0187 §3 D7 fail-closed):

    - overlay capability 不在场 ⇒ 503 ``skill_overlay_unavailable``;
    - body 非法 / source 形状不支持 ⇒ 400;
    - 助理不存在 ⇒ 404;配置面 digest 不匹配 ⇒ 409;
    - 拉取 / 格式 / 0067 三闸拒收 ⇒ 422 ``install_rejected``;
    - 成功 ⇒ 200 + ``SkillInstallReceipt``(含四件套字段)。
    """
    overlay = _skill_overlay_from_request(request)
    if overlay is None:
        return _error_envelope(
            "skill_overlay_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.skill_overlay capability 不在已解析 profile 中",
        )
    assistant_id = str(request.path_params.get("assistant_id") or "")
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
    id="lca.plugins.transport.webserver.routes_assistants",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Register /v1/assistants CRUD REST surface (ADR-0187 §3 D7 + PR-5). "
        "Handler bodies short-circuit with HTTP 501 + COMPAT marker until "
        "lca.plugins.assistant.catalog (PR-3) binds assistant.catalog."
    ),
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
        plugin_id="lca.plugins.transport.webserver.routes_assistants",
    )


__all__ = [
    "ROUTE_SPECS",
    "assistant_jobs_root",
    "assistants_root",
    "create_assistant",
    "create_assistant_job",
    "fire_assistant_job",
    "get_assistant",
    "install_assistant_skill",
    "list_assistant_jobs",
    "list_assistants",
    "retire_assistant",
    "revise_assistant_profile",
    "setup",
]
