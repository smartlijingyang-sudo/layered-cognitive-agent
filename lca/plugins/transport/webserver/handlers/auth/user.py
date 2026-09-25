"""LCA web 面用户身份解析（ADR-0252 D4）。

信任边界：Next.js 中间件在 ``/lca-api/*`` 重写请求上注入
``x-lca-user-id``（mock 分支注入 ``local-dev-user``），并携带
``Authorization: Bearer <token>``（沿用 ``lca-local``）。

本模块只做解析与 401 判定，不持有任何状态：
- ``auth_config_of`` —— 从 ``app.state`` 读期望 token 与 dev_mode；
- ``user_id_from_request`` —— 头解析 → ``(user_id, error_response)``。

``dev_mode=True``（存量单用户行为）：token 不校验、缺用户头回落
``local-dev-user``。``dev_mode=False``：token 或用户缺失一律 401
（fail-closed，无静默兜底）。
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS

DEFAULT_DEV_USER_ID = "local-dev-user"
DEFAULT_EXPECTED_TOKEN = "lca-local"  # noqa: S105  dev 共享 token，非凭据


def _err(detail: str, *, status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "type": "auth", "detail": detail}},
        status_code=status_code,
        headers=CORS_HEADERS,
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def auth_config_of(request: Request) -> tuple[str, bool]:
    """从 ``app.state`` 读 ``(expected_token, dev_mode)``；缺省走 dev 默认。"""
    state = getattr(request, "app", None)
    if state is None:
        return DEFAULT_EXPECTED_TOKEN, True
    state_obj: Any = getattr(state, "state", None)
    expected = str(getattr(state_obj, "lca_auth_expected_token", DEFAULT_EXPECTED_TOKEN))
    dev_mode = bool(getattr(state_obj, "lca_auth_dev_mode", True))
    return expected, dev_mode


def user_id_from_request(
    request: Request,
    *,
    expected_token: str,
    dev_mode: bool,
) -> tuple[str | None, JSONResponse | None]:
    """解析请求身份。

    返回 ``(user_id, None)`` 成功；``(None, error_response)`` 失败。
    ``dev_mode`` 下 token 不校验，缺用户头回落 ``local-dev-user``。
    """
    token = _bearer_token(request) or request.headers.get("x-lca-token", "").strip()
    if not dev_mode and token != expected_token:
        return None, _err("invalid token", status_code=401, code="unauthorized")

    user_id = request.headers.get("x-lca-user-id", "").strip()
    if not user_id:
        if dev_mode:
            return DEFAULT_DEV_USER_ID, None
        return None, _err("missing x-lca-user-id", status_code=401, code="missing_user")
    return user_id, None


__all__ = [
    "DEFAULT_DEV_USER_ID",
    "DEFAULT_EXPECTED_TOKEN",
    "auth_config_of",
    "user_id_from_request",
]
