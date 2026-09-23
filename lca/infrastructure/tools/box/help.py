"""request_box_help — ADR-0248 §3.5 人闸之一：员工交还桌面给用户。

当员工在员工电脑上遇到 SSO / 2FA / 验证码 / 支付等只有用户能处理的步骤时，
调用本工具请求用户协助。调用会走 HITL 暂停路径（``HITL_TOOL_NAMES`` →
``act.approve.gate`` → ``intervene.interrupt``），等待用户处理后再恢复。

与 ``askUserQuestion`` 一致：工具本体不执行外部副作用，只返回带
``approval_request`` 的失败 Observation，让 Body 保持 Observation 契约。
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool


class RequestBoxHelpTool(Tool):
    """请求用户协助处理员工机上的交互步骤。"""

    name: ClassVar[str] = "request_box_help"
    description: ClassVar[str] = (
        "当员工在员工电脑（我的电脑）上遇到只有用户能处理的步骤时调用"
        "（例如 SSO 登录、2FA 验证码、图形验证码、支付确认）。"
        "执行会暂停，把桌面交还给用户，等待用户处理并确认。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "需要用户协助的具体事项说明",
            },
            "context": {
                "type": "string",
                "description": "可选的上下文补充（当前卡在什么位置）",
            },
        },
        "required": ["request"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 3_600

    def validate(self, args: dict[str, Any]) -> str | None:
        request = args.get("request")
        if not request or not isinstance(request, str):
            return "request 必填且为字符串"
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
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error="waiting for human approval",
            extra={
                "approval_request": {
                    "type": "request_box_help",
                    "request": args["request"],
                    "context": args.get("context") or "",
                }
            },
        )


def build_box_help_tools() -> list[Tool]:
    return [RequestBoxHelpTool()]


__all__ = ["RequestBoxHelpTool", "build_box_help_tools"]
