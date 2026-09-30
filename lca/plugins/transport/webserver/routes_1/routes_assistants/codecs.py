"""Shared JSON shaping, capability probes and COMPAT envelopes for the
``/v1/assistants`` route handlers.

The helpers live here so handler submodules stay focused on request mapping;
they are re-exported at the package root because existing tests import them
from the historical ``routes_assistants`` module path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.protocols.assistant.ownership import UserAssistantBinding
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError
from lca.plugins.transport.webserver.handlers.auth.user import (
    auth_config_of,
    user_id_from_request,
)
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import ProfilePatch

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

    Handler bodies call this helper until the ``assistant.catalog``
    capability is bound to a real implementation; the marker documents the
    delete-when condition.
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


async def _register_bridge(request: Request, assistant_id: str, client_id: str) -> str | None:
    """把新建 Home 投影成 LobeHub agents 行并回填归属（ADR-0252 D7/D8）。

    读取 ``app.state.assistant_frontend_bridge``，用浏览器会话 Cookie 调
    LobeHub ``agent.createAgent``；成功回填 ``agent_id`` 并把绑定状态置为
    ``active``。bridge 未装配 / 注册失败 ⇒ ``None``（fail-soft，保持
    ``pending``，前端可经 ``register-lobehub`` 重试）。
    """
    ownership = _ownership_from_request(request)
    app = getattr(request, "app", None)
    bridge = getattr(getattr(app, "state", None), "assistant_frontend_bridge", None)
    if ownership is None or bridge is None or not getattr(bridge, "enabled", False):
        return None
    catalog = _catalog_from_request(request)
    if catalog is None:
        return None
    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError:
        return None

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

    agent_id = None
    try:
        agent_id = await bridge.register(
            assistant_id=assistant_id,
            name=spec.profile_name,
            description=spec.profile_description,
            emoji=emoji,
            system_role=soul,
            opening_message=opening_message,
            client_id=client_id,
            cookie=request.headers.get("cookie"),
        )
    except Exception:  # bridge 自身异常统一 fail-soft
        agent_id = None
    if agent_id:
        ownership.set_agent_id(assistant_id, agent_id)
    return agent_id


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
