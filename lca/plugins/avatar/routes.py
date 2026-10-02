"""Avatar REST 路由（ADR-0269 §5 / spec §9）。

端点：
- GET  /v1/assistants/{id}/avatar                        → AvatarState
- GET  /v1/assistants/{id}/avatar/candidates             → 候选列表
- POST /v1/assistants/{id}/avatar/candidates             → {user_request, reference_image?}；
                                                          有 reference_image → edit，否则 create
- POST /v1/assistants/{id}/avatar/set                    → {candidate_id} → AvatarActiveBundle
- POST /v1/assistants/{id}/avatar/clear                → AvatarState
- GET  /v1/assistants/{id}/avatar/files/{path:path}      → 文件字节（png/mp4）

鉴权（ADR-0252 D4/D6）：所有路由复用 ``routes_assistants/standing_files.py``
模式——Bearer token + ``x-lca-user-id`` 解析用户，再经 ``assistant_ownership``
做归属校验；未认证 401，非 owner 一律 404（不泄露存在性）。

错误语义（spec §9）：非法参数 400；候选不存在/过期 409；assistant 不存在 404；
路径穿越 400。文件路由用 ``{path:path}`` 才能捕获 ``candidates/<id>/<size>.png``
中的斜杠；Content-Type 按扩展名区分 ``image/png`` / ``video/mp4``。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.routing import RouteSpec
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route.register import register_routes


def _assistant_id(request: Any) -> str:
    return str(request.path_params["id"])


def _avatar_registry() -> Any:
    from lca.plugins.avatar.registry import avatar_service_registry

    return avatar_service_registry


def _json(payload: dict[str, Any], *, status_code: int = 200) -> Any:
    from starlette.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _error(code: str, *, status_code: int, error_type: str, detail: str = "") -> Any:
    payload: dict[str, Any] = {"error": {"code": code, "type": error_type}}
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=status_code)


# ── 鉴权与归属（ADR-0252 D4/D6，与 standing_files 同型） ─────────


def _user_from_request(request: Any) -> tuple[str | None, Any]:
    """解析请求身份；成功 ``(user_id, None)``，失败 ``(None, JSONResponse)``。"""
    from lca.plugins.transport.webserver.handlers.auth.user import (
        auth_config_of,
        user_id_from_request,
    )

    expected_token, dev_mode = auth_config_of(request)
    return user_id_from_request(request, expected_token=expected_token, dev_mode=dev_mode)


def _is_dev_mode(request: Any) -> bool:
    from lca.plugins.transport.webserver.handlers.auth.user import auth_config_of

    _, dev_mode = auth_config_of(request)
    return dev_mode


def _ownership_from_request(request: Any) -> Any | None:
    """读 ``app.state.assistant_ownership``；未装配返回 ``None``。"""
    app = getattr(request, "app", None)
    if app is None:
        return None
    state = getattr(app, "state", None)
    if state is None:
        return None
    return getattr(state, "assistant_ownership", None)


def _ownership_error(request: Any, user_id: str, assistant_id: str) -> Any | None:
    """归属校验（ADR-0252 D6）：非 owner 一律 404（不泄露存在性）。"""
    if _is_dev_mode(request):
        return None
    ownership = _ownership_from_request(request)
    if ownership is None:
        return None
    owner = ownership.owner_of(assistant_id)
    if owner is None or owner != user_id:
        return _error(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail="assistant 不存在",
        )
    return None


def _auth_prelude(request: Any) -> tuple[str, str, Any]:
    """鉴权 + 归属校验；成功返回 ``(user_id, assistant_id, None)``。"""
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return "", "", auth_error
    assistant_id = _assistant_id(request)
    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return "", "", ownership_error
    return user_id, assistant_id, None


def _resolve_service(assistant_id: str) -> tuple[Any, Any]:
    """按 assistant_id 解析服务；失败返回 ``(None, error_response)``。"""
    try:
        return _avatar_registry().get(assistant_id), None
    except KeyError:
        return (
            None,
            _error(
                "assistant_not_found",
                status_code=404,
                error_type="not_found",
                detail=f"assistant 不存在: {assistant_id}",
            ),
        )


# ── 端点 ───────────────────────────────────────────────────


async def get_avatar(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar`` —— 返回 AvatarState。"""
    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    service, error = _resolve_service(assistant_id)
    if error is not None:
        return error
    state = await service.get(assistant_id)
    return _json(state.model_dump(mode="json"))


async def get_candidates(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar/candidates`` —— 返回候选列表。"""
    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    service, error = _resolve_service(assistant_id)
    if error is not None:
        return error
    state = await service.get(assistant_id)
    return _json({"candidates": [c.model_dump(mode="json") for c in state.candidates]})


async def post_candidates(request: Any) -> Any:
    """``POST /v1/assistants/{id}/avatar/candidates`` —— create 或 edit。

    body ``{user_request, reference_image?}``：reference_image 为 base64 字符串时
    走 ``service.edit``（图生图），否则 ``service.create``。非字符串的
    ``user_request`` / ``reference_image`` 一律 400。
    """
    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    service, error = _resolve_service(assistant_id)
    if error is not None:
        return error

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    raw_user_request = body.get("user_request")
    if not isinstance(raw_user_request, str) or not raw_user_request.strip():
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="user_request 必填且必须为字符串",
        )
    user_request = raw_user_request.strip()

    reference_image = body.get("reference_image")
    if reference_image is not None and not isinstance(reference_image, str):
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="reference_image 必须为 base64 字符串",
        )
    try:
        if reference_image:
            import base64
            import binascii

            try:
                reference = base64.b64decode(reference_image)
            except (ValueError, binascii.Error) as exc:
                return _error(
                    "invalid_request",
                    status_code=400,
                    error_type="invalid_request",
                    detail=f"reference_image 不是合法 base64: {exc}",
                )
            candidates = await service.edit(assistant_id, user_request, reference_image=reference)
        else:
            candidates = await service.create(assistant_id, user_request)
    except ValueError as exc:
        # 服务层的 ValueError（无效参数）→ 400。
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )
    return _json({"candidates": [c.model_dump(mode="json") for c in candidates]})


async def candidates_dispatcher(request: Any) -> Any:
    """``/v1/assistants/{id}/avatar/candidates`` 方法分发（共享路径）。"""
    method = str(getattr(request, "method", "")).upper()
    if method == "GET":
        return await get_candidates(request)
    if method == "POST":
        return await post_candidates(request)
    if method == "OPTIONS":
        return _json({})
    return _error(
        "method_not_allowed",
        status_code=405,
        error_type="method_not_allowed",
        detail=f"Unsupported method {method}",
    )


async def post_set(request: Any) -> Any:
    """``POST /v1/assistants/{id}/avatar/set`` —— 激活候选并返回 bundle。

    候选不存在或已过期 → 409。``candidate_id`` 必须为字符串。
    """
    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    service, error = _resolve_service(assistant_id)
    if error is not None:
        return error

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )
    raw_candidate_id = body.get("candidate_id")
    if not isinstance(raw_candidate_id, str) or not raw_candidate_id.strip():
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="candidate_id 必填且必须为字符串",
        )
    candidate_id = raw_candidate_id.strip()

    try:
        bundle = await service.set(assistant_id, candidate_id)
    except ValueError as exc:
        return _error(
            "conflict",
            status_code=409,
            error_type="conflict",
            detail=str(exc),
        )
    return _json(bundle.model_dump(mode="json"))


async def post_clear(request: Any) -> Any:
    """``POST /v1/assistants/{id}/avatar/clear`` —— 恢复默认头像。"""
    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    service, error = _resolve_service(assistant_id)
    if error is not None:
        return error
    state = await service.clear(assistant_id)
    return _json(state.model_dump(mode="json"))


async def get_avatar_file(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar/files/{path}`` —— 白名单文件字节。

    Content-Type 按扩展名区分：``.png`` → ``image/png``，``.mp4`` → ``video/mp4``。
    """
    from lca.plugins.avatar.store import resolve_safe_path

    _, assistant_id, error = _auth_prelude(request)
    if error is not None:
        return error
    rel_path = str(request.path_params["path"])
    try:
        data = resolve_safe_path(assistant_id, rel_path)
    except ValueError as exc:
        # 路径穿越 / 非白名单 / 绝对路径 / null 字节 → 400。
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail=str(exc),
        )
    except FileNotFoundError:
        return _error(
            "file_not_found",
            status_code=404,
            error_type="not_found",
            detail=f"avatar 文件不存在: {rel_path}",
        )
    return _file_response(data, rel_path)


def _file_response(data: bytes, rel_path: str) -> Any:
    """按文件扩展名返回字节响应（png → image/png，mp4 → video/mp4）。"""
    from starlette.responses import Response

    content_type = "video/mp4" if rel_path.endswith(".mp4") else "image/png"
    return Response(content=data, media_type=content_type, headers=CORS_HEADERS)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/assistants/{id}/avatar", get_avatar, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/assistants/{id}/avatar/candidates",
        candidates_dispatcher,
        ("GET", "POST", "OPTIONS"),
    ),
    RouteSpec("/v1/assistants/{id}/avatar/set", post_set, ("POST", "OPTIONS")),
    RouteSpec("/v1/assistants/{id}/avatar/clear", post_clear, ("POST", "OPTIONS")),
    RouteSpec(
        "/v1/assistants/{id}/avatar/files/{path:path}",
        get_avatar_file,
        ("GET", "OPTIONS"),
    ),
)


async def setup(ctx: Any, config: Any) -> None:
    """注册 avatar REST 路由（由 avatar 插件装配调用）。"""
    del config
    registry = ctx.require("route_registry")
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-avatar-routes")


__all__ = ["ROUTE_SPECS", "setup"]
