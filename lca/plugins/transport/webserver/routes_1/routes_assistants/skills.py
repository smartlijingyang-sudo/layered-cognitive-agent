"""Skill-overlay endpoint for ``/v1/assistants`` (PR-6).

``POST /v1/assistants/{assistant_id}/skills:install`` maps the body
``source`` onto :class:`SkillSource` and drives ``overlay.install``,
translating capability / catalog / import errors into the fail-closed
status-code contract (ADR-0187 §3 D7).
"""

from __future__ import annotations

import dataclasses

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.protocols.memory.operational_skills import SkillImportError
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
    AssistantDigestMismatch,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _error_envelope,
    _json,
    _ownership_error,
    _parse_skill_source,
    _skill_overlay_from_request,
    _user_from_request,
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
    assistant_id = str(request.path_params.get("assistant_id") or "")

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    overlay = _skill_overlay_from_request(request)
    if overlay is None:
        return _error_envelope(
            "skill_overlay_unavailable",
            status_code=503,
            error_type="service_unavailable",
            detail="assistant.skill_overlay capability 不在已解析 profile 中",
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
