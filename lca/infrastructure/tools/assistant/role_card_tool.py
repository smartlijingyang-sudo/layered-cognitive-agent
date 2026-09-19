"""list_role_cards tool —— 创建助理向导的角色卡枚举工具面。

模型经 function calling 触发本工具枚举角色卡目录（部门→角色两级浏览 +
关键词搜索），避免为列出角色而误用文件类工具。数据形状与
``/v1/role-cards`` REST API 一致（``DepartmentSummary`` / ``RoleIndexEntry``）。
"""

from __future__ import annotations

import time
from typing import Any, ClassVar, Literal

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.assistant.role_resolver import RoleCardResolver
from lca.contracts.protocols.collaboration.casting.casting import RoleIndexEntry

ROLE_CARD_LIST_TOOL = "list_role_cards"


class RoleCardListTool(Tool):
    """列出角色卡目录：部门列表 / 部门角色 / 关键词搜索。"""

    name = ROLE_CARD_LIST_TOOL
    description = (
        "列出角色卡目录（268 个专家角色，按部门→角色两级浏览，支持关键词搜索）。"
        "创建助理向导中：无参数返回部门列表；department 参数返回该部门下角色列表；"
        "keyword 参数按角色标题/描述搜索。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "department": {"type": "string", "description": "部门 id（如 engineering）"},
            "keyword": {"type": "string", "description": "搜索关键词"},
        },
    }
    is_idempotent = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, *, resolver: RoleCardResolver | None) -> None:
        self._resolver = resolver

    def validate(self, args: dict[str, Any]) -> str | None:
        department = args.get("department")
        if department is not None and (not isinstance(department, str) or not department.strip()):
            return "department 必须是非空字符串"
        keyword = args.get("keyword")
        if keyword is not None and (not isinstance(keyword, str) or not keyword.strip()):
            return "keyword 必须是非空字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)
        if self._resolver is None:
            return self._fail(start, "角色卡库不可用（roles/ 缺失或解析失败）")

        department = str(args.get("department") or "").strip() or None
        keyword = str(args.get("keyword") or "").strip() or None

        if keyword:
            entries = self._resolver.search(keyword)
            if department:
                entries = tuple(e for e in entries if e.department == department)
            payload: dict[str, Any] = {
                "department": department,
                "keyword": keyword,
                "roles": [_role_dict(e) for e in entries],
            }
        elif department:
            entries = self._resolver.list_by_department(department)
            payload = {
                "department": department,
                "keyword": None,
                "roles": [_role_dict(e) for e in entries],
            }
        else:
            payload = {
                "departments": [
                    {"department_id": d.department_id, "label": d.label, "count": d.count}
                    for d in self._resolver.list_departments()
                ]
            }

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
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


def _role_dict(entry: RoleIndexEntry) -> dict[str, str]:
    """把 ``RoleIndexEntry`` 转成 JSON 友好字典。"""
    return {
        "role_id": entry.role_id,
        "title": entry.title,
        "department": entry.department,
        "summary": entry.summary,
        "emoji": entry.emoji,
    }


__all__ = ["ROLE_CARD_LIST_TOOL", "RoleCardListTool"]
