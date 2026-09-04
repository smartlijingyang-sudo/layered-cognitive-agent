"""create_assistant tool — ADR-0187 §3 D12 对话创建助理的执行面。

G7 窄门工具：LLM 经 function calling 触发，副作用（Home 物化 + 前端
agents 行投影）全部经本工具发生，认知内核不直接写世界。

组装链：``AssistantCatalog.create``（配置真值，发 ``assistant.created``
EP；带 ``seed_user_md`` 时完成 BOOTSTRAP 并发 ``assistant.bootstrap.completed``）
→ ``AssistantFrontendBridge.register``（前端可见性投影，fail-soft）。

Failure 语义：
- 参数缺失 / 未知 template ⇒ success=False + ``FAILURE_KIND_VALIDATION``；
- catalog 失败（磁盘/权限）⇒ success=False，错误原文透传；
- 前端注册失败 ⇒ **仍 success=True**，``frontend_agent_id=None``
  （创建真值已落 Home；降级信息由调用方转述给用户）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.plugins.assistant._home_layout import known_template_ids

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import (
        AssistantCatalog,
    )
    from lca.plugins.assistant.webserver_bridge import AssistantFrontendBridge

CREATE_ASSISTANT_TOOL = "create_assistant"


class AssistantCreateTool(Tool):
    """创建一个新助理：物化 AssistantHome 并（尽力）注册前端入口。"""

    name = CREATE_ASSISTANT_TOOL
    description = (
        "创建一个新助理（个人助手）：在后端初始化其人设/目标/技能配置，"
        "并在前端助理列表注册入口。用户想「创建助理/新建助手」时使用。"
        "参数: name（助理名字，必填）、description（一句话职责）、"
        "template_id（角色模板：assistant.default/assistant.research/"
        "assistant.writing/assistant.coding/assistant.translation/"
        "assistant.daily）、seed_user_md（可选：用户画像，提供则视为"
        "引导式创建并完成 BOOTSTRAP）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "助理名字（用户确认过的）"},
            "description": {"type": "string", "description": "一句话职责描述"},
            "template_id": {
                "type": "string",
                "description": "角色模板 id；默认 assistant.default",
            },
            "seed_user_md": {
                "type": "string",
                "description": "可选：服务对象画像（USER.md 内容）",
            },
        },
        "required": ["name"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        bridge: AssistantFrontendBridge | None = None,
    ) -> None:
        self._catalog = catalog
        self._bridge = bridge

    def validate(self, args: dict[str, Any]) -> str | None:
        name = args.get("name")
        if not isinstance(name, str) or not name.strip():
            return "name 必须是非空字符串"
        template_id = args.get("template_id") or "assistant.default"
        if template_id not in known_template_ids():
            return f"未知 template_id={template_id!r};可选: {', '.join(known_template_ids())}"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)

        from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

        name = str(args["name"]).strip()
        description = str(args.get("description") or "").strip()
        template_id = str(args.get("template_id") or "assistant.default")
        seed_user_md = args.get("seed_user_md")
        seed = str(seed_user_md).strip() if isinstance(seed_user_md, str) else None

        try:
            handle = self._catalog.create(
                CreateAssistantRequest(
                    name=name,
                    description=description,
                    template_id=template_id,
                    seed_user_md=seed or None,
                )
            )
        except Exception as exc:  # catalog raises typed AssistantCatalogError
            return self._fail(start, f"创建失败: {exc}")

        profile = _read_profile(handle.home_path)
        emoji = str(profile.get("emoji") or "🤖")
        soul_summary = _read_text(handle.home_path, "SOUL.md")

        frontend_agent_id: str | None = None
        if self._bridge is not None:
            frontend_agent_id = await self._bridge.register(
                assistant_id=handle.assistant_id,
                name=name,
                description=description or str(profile.get("description", "")),
                emoji=emoji,
                system_role=soul_summary,
                opening_message=f"你好，我是{name}。{description}".strip(),
            )

        payload: dict[str, Any] = {
            "assistant_id": handle.assistant_id,
            "home_path": handle.home_path,
            "revision_seq": handle.revision_seq,
            "template_id": template_id,
            "name": name,
            "description": description,
            "emoji": emoji,
            "capabilities": _capabilities_for(template_id),
            "bootstrap_completed": bool(seed),
            "frontend_agent_id": frontend_agent_id,
            "frontend_url": f"/agent/{frontend_agent_id}" if frontend_agent_id else None,
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


def _read_profile(home_path: str) -> dict[str, Any]:
    """读 Home 的 profile.json（emoji/description 回显用）；失败返回空。"""
    try:
        raw = json.loads((Path(home_path) / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_text(home_path: str, filename: str) -> str:
    try:
        return (Path(home_path) / filename).read_text(encoding="utf-8")
    except OSError:
        return ""


def _capabilities_for(template_id: str) -> str:
    """模板 → 一句话能力摘要（回复用户用）。"""
    table = {
        "assistant.default": "通用助理：问答、整理信息、协助日常任务",
        "assistant.research": "研究助理：资料搜集、交叉核验、带引用的研究报告",
        "assistant.writing": "写作助理：起草、润色、结构化成稿",
        "assistant.coding": "编程助理：读写代码、调试、解释实现",
        "assistant.translation": "翻译助理：中英互译、本地化、术语一致",
        "assistant.daily": "日程助理：计划、提醒清单、阶段性总结",
    }
    return table.get(template_id, table["assistant.default"])


__all__ = ["CREATE_ASSISTANT_TOOL", "AssistantCreateTool"]
