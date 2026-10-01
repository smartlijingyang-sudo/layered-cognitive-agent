"""Onboarding naming tools (INV-03, INV-06, INV-07).

Provides:
- CreateNameWidgetTool: records user_name to user_store (SSOT) & assistant Home (USER.md),
  and returns a structured NamingWidgetPayload with embed_token.
- UpdateIdentityTool: updates assistant profile and IDENTITY.md via catalog.revise_profile,
  marks onboarding completed in user_store, and emits celebratory reaction.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.onboarding.naming import NamingCandidate, NamingWidgetPayload
from lca.contracts.protocols import Tool
from lca.contracts.protocols.assistant.catalog import ProfilePatch

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import AssistantCatalog
    from lca.contracts.protocols.assistant.ownership import AssistantOwnership

CREATE_NAME_WIDGET_TOOL = "create_name_widget"
UPDATE_IDENTITY_TOOL = "update_identity"

_DEFAULT_CANDIDATE_POOL = (
    NamingCandidate(id="cand_athena", name="Athena", vibe="敏锐专注、行事果决", emoji="🦉"),
    NamingCandidate(id="cand_nova", name="星澜", vibe="沉稳严谨、善于统揽", emoji="🌟"),
    NamingCandidate(id="cand_echo", name="回响", vibe="倾听敏捷、随叫随到", emoji="🌊"),
    NamingCandidate(id="cand_spark", name="知微", vibe="见微知著、执行力强", emoji="⚡"),
)


class _BaseOnboardingTool(Tool):
    """Shared scaffolding for onboarding tools."""

    namespace: ClassVar[str] = "agent"
    required_grant: ClassVar[str] = "profile.revise"
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        assistant_id: str,
        user_store: AssistantOwnership | None = None,
        user_id: str | None = None,
    ) -> None:
        self._catalog = catalog
        self._assistant_id = assistant_id
        if user_store is None:
            user_store = getattr(catalog, "_user_store", None)
        if user_id is None:
            import contextlib
            import json
            from pathlib import Path

            with contextlib.suppress(Exception):
                spec = catalog.get(assistant_id)
                manifest_path = Path(spec.home_path) / "manifest.json"
                if manifest_path.is_file():
                    m = json.loads(manifest_path.read_text(encoding="utf-8"))
                    user_id = m.get("user_id")
        self._user_store = user_store
        self._user_id = user_id

    def _ok(self, start: float, payload: dict[str, Any] | None, text: str = "") -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=payload,
            content_type=ContentType.STRUCTURED if payload else ContentType.TEXT,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def _fail(self, start: float, message: str) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=message,
            latency_ms=int((time.monotonic() - start) * 1000),
            extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
        )


class CreateNameWidgetTool(_BaseOnboardingTool):
    """Record user name to DB + Home and generate naming widget token."""

    name = CREATE_NAME_WIDGET_TOOL
    description = (
        "记录用户姓名并生成起名交互 Widget 卡片。"
        "将 user_name 沉淀到数据库与当前助理的 USER.md，并返回候选助理名与 Widget Token。"
        "参数: user_name (必填，用户姓名或称谓)，keep_muse (可选，是否保留 Muse 固定选项)。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "user_name": {"type": "string", "description": "用户的姓名或称呼"},
            "keep_muse": {"type": "boolean", "description": "是否保留 Muse 固定选项，默认 false"},
        },
        "required": ["user_name"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        user_name = str(args.get("user_name") or "").strip()
        if not user_name:
            return self._fail(start, "user_name 必须为非空字符串")
        keep_muse = bool(args.get("keep_muse", False))

        user_md = f"# USER.md\n\n- **Name:** {user_name}\n- **Role:** User\n"

        # 1. 写入数据库 SSOT (INV-02)
        if self._user_store is not None and self._user_id:
            try:
                self._user_store.update_user_md(self._user_id, user_md, display_name=user_name)
            except Exception as exc:
                return self._fail(start, f"写入数据库用户画像失败: {exc}")

        # 2. 经 Catalog revise_profile 写入当前助理 Home 的 USER.md (INV-03)
        try:
            self._catalog.revise_profile(
                self._assistant_id,
                ProfilePatch(user_md=user_md),
                actor="onboarding",
            )
        except Exception as exc:
            return self._fail(start, f"更新助理 USER.md 失败: {exc}")

        # 3. 构造起名 Widget
        token = f"widget_name_{uuid.uuid4().hex[:12]}"
        candidates = _DEFAULT_CANDIDATE_POOL[:2]
        payload = NamingWidgetPayload(
            token=token,
            assistant_id=self._assistant_id,
            candidates=candidates,
            allow_custom=True,
            keep_muse=keep_muse,
        )
        widget_tag = f"[widget:name_picker?token={token}]"

        return self._ok(
            start,
            payload={
                "token": token,
                "assistant_id": self._assistant_id,
                "user_name": user_name,
                "candidates": [c.model_dump() for c in payload.candidates],
                "widget_tag": widget_tag,
                "message": f"已记录你的名字为「{user_name}」，并生成了起名交互卡片：{widget_tag}",
            },
        )


class UpdateIdentityTool(_BaseOnboardingTool):
    """Set assistant identity (name, vibe, emoji), mark completed, and celebrate."""

    name = UPDATE_IDENTITY_TOOL
    description = (
        "为当前助理确立名字与人设，写盘 IDENTITY.md 与 profile.json，标记迎新完成并追加庆祝 Reaction。"
        "参数: name (必填，助理名字)，vibe (可选，风格调性)，emoji (可选，表情)。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "新选定的助理名字"},
            "vibe": {"type": "string", "description": "助理风格调性"},
            "emoji": {"type": "string", "description": "助理代表 Emoji"},
        },
        "required": ["name"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        name = str(args.get("name") or "").strip()
        if not name:
            return self._fail(start, "name 必须为非空字符串")
        vibe = str(args.get("vibe") or "helpful, sharp, proactive").strip()
        emoji = str(args.get("emoji") or "🦉").strip()

        identity_md = (
            f"# IDENTITY.md\n\n"
            f"- **Name:** {name}\n"
            f"- **Character:** AI personal agent\n"
            f"- **Vibe:** {vibe}\n"
            f"- **Emoji:** {emoji}\n"
        )

        # 1. 经 Catalog revise_profile 写入 profile.json 与 IDENTITY.md (INV-03, INV-07)
        try:
            self._catalog.revise_profile(
                self._assistant_id,
                ProfilePatch(
                    profile_name=name,
                    identity_md=identity_md,
                ),
                actor="onboarding",
            )
        except Exception as exc:
            return self._fail(start, f"更新助理身份失败: {exc}")

        # 2. 标记用户 onboarding 状态为 completed (INV-01)
        if self._user_store is not None and self._user_id:
            try:
                self._user_store.set_onboarding_state(self._user_id, "completed")
            except Exception as exc:
                return self._fail(start, f"标记 onboarding 完成状态失败: {exc}")

        return self._ok(
            start,
            payload={
                "assistant_id": self._assistant_id,
                "name": name,
                "vibe": vibe,
                "emoji": emoji,
                "reaction": "🎉",
                "onboarding_state": "completed",
                "message": f"助理已正式命名为「{name}」，IDENTITY.md 已落盘，双向迎新顺利完成！",
            },
        )
