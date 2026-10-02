"""React-to-message tool (Muse-aligned react_to_user_message).

Lets the agent attach a single emoji reaction to any message, independent
of the text reply. The frontend renders it as a small badge on the message
corner. Typical scenarios:

- 确认：任务接单时给用户消息贴 👍（"收到了"不占一个气泡）；
- 庆祝：改名/完成里程碑时贴 🎉；
- 共情：用户分享喜事时贴 ❤️；
- 俏皮：轻松时刻贴 😄（克制使用）。

Reaction 与文字回复正交：贴 reaction 不产生新气泡，不打断对话流。
"""

from __future__ import annotations

import time
from typing import Any, ClassVar, Literal

from pydantic import ValidationError

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.messaging.reaction import MessageReaction
from lca.contracts.protocols import Tool
from lca.infrastructure.messaging.reaction_store import ReactionStore

REACT_TO_MESSAGE_TOOL = "react_to_message"


class ReactToMessageTool(Tool):
    """Attach an emoji reaction to a message."""

    name = REACT_TO_MESSAGE_TOOL
    namespace: ClassVar[str] = "agent"
    required_grant: ClassVar[str] = "message.react"
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    description = (
        "给任意消息贴一个 emoji reaction（如用户消息贴 👍 表示收到，改名成功贴 🎉 庆祝）。"
        "Reaction 独立于文字回复，前端渲染为消息角落的小徽标，不产生新气泡。"
        "参数: message_id (必填，目标消息 ID)，emoji (必填，单个 emoji)。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "目标消息 ID"},
            "emoji": {"type": "string", "description": "单个 emoji，如 🎉 / 👍 / ❤️"},
        },
        "required": ["message_id", "emoji"],
    }

    def __init__(self, *, store: ReactionStore | None = None) -> None:
        self._store = store or ReactionStore()

    def _ok(self, start: float, payload: dict[str, Any] | None) -> Observation:
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

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        message_id = str(args.get("message_id") or "")
        emoji = str(args.get("emoji") or "")

        try:
            reaction = MessageReaction(message_id=message_id, emoji=emoji)
        except ValidationError as exc:
            return self._fail(start, f"reaction 参数非法: {exc.errors()[0]['msg']}")

        self._store.add(reaction)
        return self._ok(
            start,
            payload={
                "message_id": reaction.message_id,
                "emoji": reaction.emoji,
                "actor": reaction.actor,
                "message": f"已在消息 {reaction.message_id} 上贴 {reaction.emoji}",
            },
        )
