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

def _app_state_attr(request: Request, attr: str) -> Any | None:
    """request.app.state.<attr> 的空安全读取（app/state 缺省时回 None）。"""
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, attr, None)

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
    resolver = _app_state_attr(request, "role_card_resolver")
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
            if (package_root / "SKILL.md").is_file() and (package_root / "manifest.json").is_file():
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

async def onboarding_welcome(request: Request) -> JSONResponse:
    """``GET /v1/onboarding/welcome`` —— 首次迎新 / 打招呼话术（两阶段同构）。"""
    expected_token, dev_mode = auth_config_of(request)
    user_id, auth_error = user_id_from_request(
        request, expected_token=expected_token, dev_mode=dev_mode
    )
    if auth_error is not None:
        return auth_error

    user_store = _app_state_attr(request, "assistant_ownership")
    state = user_store.get_onboarding_state(user_id) if user_store else "pending"

    user_name = ""
    if user_store and state == "completed":
        from lca.application.onboarding.script import extract_user_name_from_user_md

        user_name = extract_user_name_from_user_md(user_store.get_user_md(user_id) or "")

    assistant_id = str(request.query_params.get("assistant_id") or "").strip()
    assistant_name = str(request.query_params.get("assistant_name") or "")
    if not assistant_name and assistant_id:
        catalog = _app_state_attr(request, "assistant_catalog")
        if catalog is not None:
            import contextlib

            with contextlib.suppress(Exception):
                spec = catalog.get(assistant_id)
                if spec and spec.profile_name:
                    assistant_name = spec.profile_name
    if not assistant_name:
        assistant_name = "小助"

    role_title = str(request.query_params.get("role_title") or "专属")
    locale = str(request.query_params.get("locale") or request.headers.get("accept-language") or "en")

    from lca.application.onboarding.script import get_onboarding_opening_messages

    msgs = get_onboarding_opening_messages(
        user_state=state,
        user_name=user_name,
        assistant_name=assistant_name,
        role_title=role_title,
        locale=locale,
    )

    return _json(
        {
            "user_id": user_id,
            "onboarding_state": state,
            "messages": list(msgs),
            "step": "ask_user_name" if state == "pending" else "assistant_ready",
            "user_name": user_name,
        },
        status_code=200,
    )

async def onboarding_naming_settle(request: Request) -> JSONResponse:
    """``POST /v1/onboarding/naming/settle`` —— 前端起名 Widget 确认命名并落盘。"""
    expected_token, dev_mode = auth_config_of(request)
    user_id, auth_error = user_id_from_request(
        request, expected_token=expected_token, dev_mode=dev_mode
    )
    if auth_error is not None:
        return auth_error

    try:
        body = await request.json()
    except Exception:
        return _error("invalid_json", status_code=400, code="invalid_request")

    if not isinstance(body, dict):
        return _error("body 必须是 JSON object", status_code=400, code="invalid_request")

    assistant_id = str(body.get("assistant_id") or "").strip()
    name = str(body.get("name") or "").strip()
    vibe = str(body.get("vibe") or "").strip()

    if not name:
        return _error("name 必须为非空字符串", status_code=400, code="invalid_request")

    # 1. 沉淀至 user_store 权威库：标记迎新已完成
    user_store = _app_state_attr(request, "assistant_ownership")
    if user_store is not None:
        user_store.set_onboarding_state(user_id, "completed")

    # 2. 同步至当前助理 Home（IDENTITY.md 与 profile.json）
    catalog = _app_state_attr(request, "assistant_catalog")
    if catalog is not None and assistant_id:
        try:
            from lca.contracts.protocols.assistant.catalog import ProfilePatch

            identity_content = (
                f"# IDENTITY.md - Assistant Identity\n\n"
                f"- **Name:** {name}\n"
                f"- **Vibe:** {vibe or '专属'}\n"
            )
            catalog.revise_profile(
                assistant_id,
                ProfilePatch(
                    profile_name=name,
                    identity_md=identity_content,
                ),
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("failed to revise profile during naming settle: %s", exc)

    # 3. 主动欢迎消息：由本响应携带（RESPONSE_CARRIED），前端直接渲染为
    #    assistant 气泡。走 WorthinessGate 裁决（requested=True 必达）。
    #    失败不炸主流程（fail-soft）：settle 的核心是落盘已完成。
    welcome_message: str | None = None
    try:
        from lca.application.onboarding.script import get_onboarding_opening_messages
        from lca.cognition.proactive import decide as _decide_worthiness
        from lca.contracts.models.proactive import (
            DeliveryTarget,
            DeliveryTargetKind,
            ProactiveMessage,
            ProactiveRequest,
            ProactiveSource,
            VerdictKind,
        )
        from lca.infrastructure.proactive import ProactiveDeliverer

        _locale = str(request.headers.get("accept-language") or "zh")
        _bubbles = get_onboarding_opening_messages(
            user_state="completed",
            assistant_name=name,
            locale=_locale,
        )
        _target = DeliveryTarget(kind=DeliveryTargetKind.RESPONSE_CARRIED)
        # requested 的 trigger 上下文背书：本请求刚刚完成了该 user_id 的
        # onboarding（上文已落盘），引用与背书都来自这次真实完成的事件，
        # 不是消息生产方的自声明（ADR-0264 §4①）。
        _event_ref = f"onboarding-completed:{user_id}"
        _request = ProactiveRequest(
            message=ProactiveMessage(
                id=f"onboarding-welcome-{user_id}",
                content=_bubbles[0],
                source=ProactiveSource.ONBOARDING_COMPLETED,
            ),
            target=_target,
            requested=True,
            request_ref=_event_ref,
            known_request_refs=(_event_ref,),
            declared=VerdictKind.DELIVER_CHAT,
        )
        _verdict = _decide_worthiness(_request)
        if _verdict.kind == VerdictKind.DELIVER_CHAT:
            _receipt = ProactiveDeliverer().deliver(
                _request.message,
                _target,
                annotate_unretrieved=_verdict.annotate_unretrieved,
            )
            welcome_message = _receipt["carried_message"]["content"]
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "onboarding welcome message failed; response continues without it",
            exc_info=True,
        )

    # 4. 改名后固定流程（对齐 Muse）：庆祝 → 能力介绍 → 连接引导。
    #    固定文案来自 script.get_post_naming_messages，requested=True 必达，
    #    走同样的 WorthinessGate/ProactiveDeliverer 模式。
    #    失败 fail-soft：settle 核心（落盘）已完成，不炸主流程。
    followup_messages: list[str] = []
    try:
        from lca.application.onboarding.script import get_post_naming_messages
        from lca.cognition.proactive import decide as _decide_followup
        from lca.contracts.models.proactive import (
            DeliveryTarget as _FollowupTarget,
            DeliveryTargetKind as _FollowupTargetKind,
            ProactiveMessage as _FollowupMessage,
            ProactiveRequest as _FollowupRequest,
            ProactiveSource as _FollowupSource,
            VerdictKind as _FollowupVerdict,
        )
        from lca.infrastructure.proactive import ProactiveDeliverer as _FollowupDeliverer

        _followup_locale = str(request.headers.get("accept-language") or "zh")
        _followup_event_ref = f"onboarding-completed:{user_id}"
        for _idx, _bubble in enumerate(
            get_post_naming_messages(
                assistant_name=name,
                locale=_followup_locale,
            )
        ):
            _freq = _FollowupRequest(
                message=_FollowupMessage(
                    id=f"onboarding-postnaming-{user_id}-{_idx}",
                    content=_bubble,
                    source=_FollowupSource.ONBOARDING_COMPLETED,
                ),
                target=_FollowupTarget(kind=_FollowupTargetKind.RESPONSE_CARRIED),
                requested=True,
                request_ref=_followup_event_ref,
                known_request_refs=(_followup_event_ref,),
                declared=_FollowupVerdict.DELIVER_CHAT,
            )
            _fverdict = _decide_followup(_freq)
            if _fverdict.kind == _FollowupVerdict.DELIVER_CHAT:
                _frecept = _FollowupDeliverer().deliver(
                    _freq.message,
                    _freq.target,
                    annotate_unretrieved=_fverdict.annotate_unretrieved,
                )
                followup_messages.append(_frecept["carried_message"]["content"])
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "onboarding post-naming followup failed; response continues without it",
            exc_info=True,
        )

    return _json(
        {
            "ok": True,
            "assistant_id": assistant_id,
            "name": name,
            "vibe": vibe,
            "reaction": "🎉",
            "welcome_message": welcome_message,
            "followup_messages": followup_messages,
            "show_connectors": True,
        },
        status_code=200,
    )

ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/onboarding/presets", onboarding_presets, ("GET", "OPTIONS")),
    RouteSpec("/v1/onboarding/welcome", onboarding_welcome, ("GET", "OPTIONS")),
    RouteSpec("/v1/onboarding/naming/settle", onboarding_naming_settle, ("POST", "OPTIONS")),
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
