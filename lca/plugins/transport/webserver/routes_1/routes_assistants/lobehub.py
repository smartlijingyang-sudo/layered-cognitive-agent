"""LobeHub integration endpoints for ``/v1/assistants`` (ADR-0252 D7/D8).

``import-lobehub`` imports a LobeHub agent JSON as a new Home;
``bind-agent`` / ``register-lobehub`` reconcile the LobeHub ``agent_id``
row with the ownership store.
"""

from __future__ import annotations

import json
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.plugins.assistant.home._home_layout import (
    build_manifest,
    load_manifest,
    write_manifest,
)
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _catalog_from_request,
    _error_envelope,
    _extract_emoji,
    _json,
    _not_implemented,
    _ownership_from_request,
    _profile_view,
    _register_bridge,
    _user_from_request,
)


def _manifest_revision_seq(manifest: dict[str, object]) -> int:
    """Return the manifest ``revision_seq`` as an int, tolerating drift."""
    raw = manifest.get("revision_seq", 0)
    return raw if isinstance(raw, int) else 0


async def import_lobehub_agent(request: Request) -> JSONResponse:
    """``POST /v1/assistants/import-lobehub`` — 从 LobeHub agent JSON 导入助理。

    LobeHub agent JSON 形态：
    ``{title, description, avatar, systemRole?, plugins?, openingMessage?}``

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

    home = Path(handle.home_path)

    if system_role:
        (home / "SOUL.md").write_text(system_role, encoding="utf-8")

    if emoji:
        profile_path = home / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["emoji"] = emoji
        profile["source"] = "lobehub"
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    manifest = load_manifest(home, handle.assistant_id)
    new_manifest = build_manifest(
        assistant_id=handle.assistant_id,
        template_id="assistant.default",
        revision_seq=_manifest_revision_seq(manifest) + (1 if system_role or emoji else 0),
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

    agent_id = await _register_bridge(request, assistant_id, f"lca-{assistant_id}")
    if agent_id is None:
        return _error_envelope(
            "bridge_registration_failed",
            status_code=502,
            error_type="bad_gateway",
            detail="LobeHub agent 行注册失败，可稍后重试",
        )
    return _json({"assistant_id": assistant_id, "agent_id": agent_id}, status_code=200)
