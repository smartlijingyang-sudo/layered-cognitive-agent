"""Avatar REST 路由（ADR-0269 §5 / spec §9）。

端点：
- GET  /v1/assistants/{id}/avatar                        → AvatarState
- GET  /v1/assistants/{id}/avatar/candidates             → 候选列表
- POST /v1/assistants/{id}/avatar/candidates             → {user_request, reference_image?}；
                                                          有 reference_image → edit，否则 create
- POST /v1/assistants/{id}/avatar/set                    → {candidate_id} → AvatarActiveBundle
- POST /v1/assistants/{id}/avatar/clear                → AvatarState
- GET  /v1/assistants/{id}/avatar/files/{path:path}      → 图片字节（image/png）

错误语义（spec §9）：非法参数 400；候选不存在/过期 409；assistant 不存在 404；
路径穿越 400。文件路由用 ``{path:path}`` 才能捕获 ``candidates/<id>/<size>.png``
中的斜杠。
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


def _png(data: bytes) -> Any:
    from starlette.responses import Response

    return Response(content=data, media_type="image/png", headers=CORS_HEADERS)


def _error(code: str, *, status_code: int, error_type: str, detail: str = "") -> Any:
    payload: dict[str, Any] = {"error": {"code": code, "type": error_type}}
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=status_code)


def _resolve_service(request: Any) -> tuple[Any, str, Any]:
    """解析 assistant_id 的 AvatarService；失败返回 (None, id, error_response)。"""
    assistant_id = _assistant_id(request)
    try:
        service = _avatar_registry().get(assistant_id)
    except KeyError:
        return (
            None,
            assistant_id,
            _error(
                "assistant_not_found",
                status_code=404,
                error_type="not_found",
                detail=f"assistant 不存在: {assistant_id}",
            ),
        )
    return service, assistant_id, None


async def get_avatar(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar`` —— 返回 AvatarState。"""
    service, assistant_id, error = _resolve_service(request)
    if error is not None:
        return error
    state = await service.get(assistant_id)
    return _json(state.model_dump(mode="json"))


async def get_candidates(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar/candidates`` —— 返回候选列表。"""
    service, assistant_id, error = _resolve_service(request)
    if error is not None:
        return error
    state = await service.get(assistant_id)
    return _json({"candidates": [c.model_dump(mode="json") for c in state.candidates]})


async def post_candidates(request: Any) -> Any:
    """``POST /v1/assistants/{id}/avatar/candidates`` —— create 或 edit。

    body ``{user_request, reference_image?}``：reference_image 为 base64 字符串时
    走 ``service.edit``（图生图），否则 ``service.create``。
    """
    service, assistant_id, error = _resolve_service(request)
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

    user_request = str(body.get("user_request") or "").strip()
    if not user_request:
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="user_request 必填",
        )

    reference_image = body.get("reference_image")
    try:
        if reference_image:
            import base64

            reference = base64.b64decode(reference_image)
            candidates = await service.edit(assistant_id, user_request, reference_image=reference)
        else:
            candidates = await service.create(assistant_id, user_request)
    except ValueError as exc:
        # 服务/解码层的 ValueError（无效参数、非法 base64）→ 400。
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

    候选不存在或已过期 → 409。
    """
    service, assistant_id, error = _resolve_service(request)
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
    candidate_id = str(body.get("candidate_id") or "")
    if not candidate_id:
        return _error(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="candidate_id 必填",
        )

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
    service, assistant_id, error = _resolve_service(request)
    if error is not None:
        return error
    state = await service.clear(assistant_id)
    return _json(state.model_dump(mode="json"))


async def get_avatar_file(request: Any) -> Any:
    """``GET /v1/assistants/{id}/avatar/files/{path}`` —— 白名单图片字节。"""
    from lca.plugins.avatar.store import resolve_safe_path

    assistant_id = _assistant_id(request)
    rel_path = str(request.path_params["path"])
    try:
        data = resolve_safe_path(assistant_id, rel_path)
    except KeyError:
        return _error(
            "assistant_not_found",
            status_code=404,
            error_type="not_found",
            detail=f"assistant 不存在: {assistant_id}",
        )
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
    return _png(data)


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
