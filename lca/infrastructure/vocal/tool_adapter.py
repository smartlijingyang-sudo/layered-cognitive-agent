"""``send_message`` 的 Tool 协议适配器（ADR-0248 gated 模式模型可见工具）。

``SendMessageTool`` 本身不是 ``lca.contracts.protocols.Tool``（execute 返回
dict），不能进入 ``ForkedTools`` / 工具注册表。本适配器把门控声带投递包装成
标准 Tool：``name`` / ``description`` / ``parameters`` / ``validate`` /
``execute -> Observation``，供 ``concept.tool.fork`` 在 gated 模式下追加到
每 Run 工具集。
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.vocal.models import VocalMessageType
from lca.contracts.protocols import Tool
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.tool import SendMessageTool

_MESSAGE_TYPES = tuple(t.value for t in VocalMessageType)


class SendMessageVocalTool(Tool):
    """ADR-0248 唯一声道的标准 Tool 适配器。"""

    name: ClassVar[str] = "send_message"
    description: ClassVar[str] = (
        "向用户对外唯一声道发射正式消息。在门控模式下，大模型普通内省文本用户不可见，"
        "必须调用此工具交付气泡或选项卡。支持类型：text（普通气泡）、"
        "widget（选项卡停等）、secret_request（敏感凭证输入）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": _MESSAGE_TYPES,
                "description": "消息投递类型",
                "default": "text",
            },
            "content": {"type": "string", "description": "正式文本气泡内容"},
            "options": {
                "type": "array",
                "items": {"type": "object"},
                "description": "widget 类型的选项卡选项（1-6 项）",
            },
            "secret_key": {"type": "string", "description": "secret_request 凭证标识键名"},
            "reply_to_id": {"type": "string", "description": "关联的上下文消息 ID"},
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, gate: VocalGateProtocol) -> None:
        self._inner = SendMessageTool(gate)

    def validate(self, args: dict[str, Any]) -> str | None:
        try:
            mtype = VocalMessageType(str(args.get("type") or "text"))
        except ValueError:
            return f"type 必须是 {_MESSAGE_TYPES} 之一"
        if mtype == VocalMessageType.TEXT and not args.get("content"):
            return "type='text' 时 content 字段不能为空"
        if mtype == VocalMessageType.WIDGET and not args.get("options"):
            return "type='widget' 时 options 必须提供"
        if mtype == VocalMessageType.SECRET_REQUEST and not args.get("secret_key"):
            return "type='secret_request' 时 secret_key 字段不能为空"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
            )
        content_val = args.get("content")
        receipt = self._inner.execute(
            type=str(args.get("type") or "text"),
            content=content_val,
            options=args.get("options"),
            secret_key=args.get("secret_key"),
            reply_to_id=args.get("reply_to_id"),
        )
        # 向 Session 追加不可变事实事件 (ADR-0248 §3.3 / ADR-0186 单轨)
        from lca.infrastructure.session.bindings import resolve_session_reader

        session = resolve_session_reader()
        if session is not None and hasattr(session, "append"):
            session.append(
                "vocal.message.delivered",
                {
                    "message_id": receipt["message_id"],
                    "vocal_type": receipt["vocal_type"],
                    "content": content_val,
                    "options": args.get("options"),
                    "secret_key": args.get("secret_key"),
                    "reply_to_id": args.get("reply_to_id"),
                },
                visibility="user",
            )

        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "status": "delivered",
                "message_id": receipt["message_id"],
                "vocal_type": receipt["vocal_type"],
                "content": content_val,
                "is_terminal_for_turn": receipt["is_terminal_for_turn"],
                "requires_user_action": receipt["requires_user_action"],
            },
        )


__all__ = ["SendMessageVocalTool"]
