"""Catalog-backed ``/v1/assistants`` profile endpoints.

Handlers here map HTTP requests onto ``AssistantCatalog`` operations and
project the serializable parts of the catalog protocol (ADR-0187 §3 D7 +
ADR-0252 ownership isolation).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
    AssistantDigestMismatch,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _bind_ownership,
    _catalog_from_request,
    _error_envelope,
    _is_dev_mode,
    _json,
    _not_implemented,
    _ownership_error,
    _ownership_from_request,
    _profile_patch_from_body,
    _profile_view,
    _register_bridge,
    _user_from_request,
)


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
    use_template_soul = body.get("use_template_soul", False)
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
    if not isinstance(use_template_soul, bool):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="use_template_soul 必须为布尔值",
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

    # ADR-0252 D3/D8 幂等：同 (user_id, client_id) 已绑定 → 返回既有助理，
    # 不重复创建 Home（修复重复 client_id 产生孤儿助理）。
    ownership = _ownership_from_request(request)
    if client_id and ownership is not None:
        existing_id = ownership.assistant_id_for_client(user_id, client_id)
        if existing_id:
            try:
                existing_spec = catalog.get(existing_id)
            except AssistantCatalogError as exc:
                return _error_envelope(
                    "invalid_request",
                    status_code=400,
                    error_type="invalid_request",
                    detail=str(exc),
                )
            return _json(
                {
                    "assistant_id": existing_spec.assistant_id,
                    "home_path": existing_spec.home_path,
                    "revision_seq": existing_spec.revision_seq,
                    "template_id": existing_spec.template_id,
                    "agent_id": ownership.agent_id_of(existing_spec.assistant_id),
                    "profile": _profile_view(existing_spec.home_path),
                },
                status_code=200,
            )

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
                use_template_soul=use_template_soul,
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

    agent_id = await _register_bridge(
        request, handle.assistant_id, client_id or f"lca-{handle.assistant_id}"
    )

    return _json(
        {
            "assistant_id": handle.assistant_id,
            "home_path": handle.home_path,
            "revision_seq": handle.revision_seq,
            "template_id": template_id,
            "agent_id": agent_id,
            "profile": _profile_view(handle.home_path),
        },
        status_code=201,
    )


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


async def reimport_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}:reimport`` —— ``catalog.reimport``.

    ADR-0187 §3 D2 定义的裸改恢复路径：以磁盘当前配置面文件为输入重算
    全部 digest ⇒ ``revision_seq++`` ⇒ 写 ``revisions/`` 快照 ⇒ 发 EP
    （``actor="reimport"``）。不校验现有 digest（正是恢复路径的用途）。

    状态码契约：

    - 身份不可解析 ⇒ 401；
    - catalog capability 不在场 ⇒ 501 ``catalog_unavailable``；
    - 未知 assistant ⇒ 404；非 owner ⇒ 404；
    - 成功 ⇒ 200 + ``PlanRevision`` 字段。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.reimport")
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    try:
        body = await request.json()
    except (ValueError, OSError):
        body = {}
    reason = "manual_reimport"
    if isinstance(body, dict):
        reason_raw = body.get("reason")
        if isinstance(reason_raw, str) and reason_raw.strip():
            reason = reason_raw.strip()[:120]

    try:
        revision = catalog.reimport(assistant_id, reason=f"api:{reason}")
        home_path = catalog.get(assistant_id).home_path
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
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


async def retire_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/retire`` —— ``catalog.retire``."""
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    assistant_id = str(request.path_params.get("assistant_id") or "")
    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.retire")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")
