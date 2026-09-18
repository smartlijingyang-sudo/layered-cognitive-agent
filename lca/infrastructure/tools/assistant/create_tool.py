"""create_assistant tool — ADR-0187 §3 D12 + ADR-0242 D1/D7 对话创建助理的执行面。

G7 窄门工具：LLM 经 function calling 触发，副作用（Home 物化 + 前端
agents 行投影）全部经本工具发生，认知内核不直接写世界。

组装链：``AssistantCatalog.create``（配置真值，发 ``assistant.created``
EP；带 ``seed_user_md`` 或 ``soul`` 时完成 BOOTSTRAP 并发
``assistant.bootstrap.completed``）→ ``AssistantFrontendBridge.register``
（前端可见性投影，fail-soft）。

Failure 语义：
- 参数缺失 / 未知 template ⇒ success=False + ``FAILURE_KIND_VALIDATION``；
- SOUL 完整度校验失败（``SoulValidationError``）⇒ success=False +
  ``FAILURE_KIND_VALIDATION``，错误消息指出缺哪一段，继续对齐；
- catalog 失败（磁盘/权限/digest）⇒ success=False，错误原文透传；
- 前端注册失败 ⇒ **仍 success=True**，``frontend_agent_id=None``
  （创建真值已落 Home；降级信息由调用方转述给用户）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import yaml

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.plugins.assistant.home._home_layout import known_template_ids

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import (
        AssistantCatalog,
    )
    from lca.plugins.assistant.webserver.bridge import AssistantFrontendBridge

CREATE_ASSISTANT_TOOL = "create_assistant"


class AssistantCreateTool(Tool):
    """创建一个新助理：物化 AssistantHome 并（尽力）注册前端入口。"""

    name = CREATE_ASSISTANT_TOOL
    description = (
        "创建一个新助理（个人助手）：在后端初始化其人设/目标/技能配置，"
        "并在前端助理列表注册入口。用户想「创建助理/新建助手」时使用。"
        "参数: name（助理名字，必填）、description（一句话职责）、"
        "from_role（可选：角色档案 role_id，如 engineering/engineering-software-architect，"
        "提供则 SOUL 从该角色卡片填充）、"
        "soul（可选：向导对齐后的最终 SOUL 全文，非空时覆盖 from_role 并必须通过完整度校验）、"
        "inherit_from（可选：继承快照来源 assistant_id，复制其技能与工具/授权策略）、"
        "template_id（角色模板：assistant.default 等，from_role 不填时使用）、"
        "seed_user_md（可选：用户画像）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "助理名字（用户确认过的）"},
            "description": {"type": "string", "description": "一句话职责描述"},
            "from_role": {
                "type": "string",
                "description": (
                    "角色档案 role_id（如 engineering/engineering-software-architect）。"
                    "提供时 SOUL.md 从该角色卡片 backstory 填充（除非 soul 参数非空），"
                    "assistant 自动获得该角色的人格。"
                ),
            },
            "soul": {
                "type": "string",
                "description": (
                    "向导对齐后的最终 SOUL 全文（Markdown，含 ## 🧠 身份 / ## 🎭 性格 / "
                    "## 🛠 能力 / ## 🗣 语气 四个核心段，去除空白后至少 200 字符）。"
                    "非空时覆盖 from_role backstory 与模板默认。"
                ),
            },
            "inherit_from": {
                "type": "string",
                "description": (
                    "继承快照来源 assistant_id（asst_ 开头）。"
                    "创建时把来源助理的技能、tools.yaml 与 grants.yaml 策略复制为新 Home 快照。"
                ),
            },
            "template_id": {
                "type": "string",
                "description": "角色模板 id；默认 assistant.default。from_role 提供时仍用模板填充其他配置面",
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
        from_role = args.get("from_role")
        soul = args.get("soul")
        inherit_from = args.get("inherit_from")
        seed = str(seed_user_md).strip() if isinstance(seed_user_md, str) else None
        role = str(from_role).strip() if isinstance(from_role, str) and from_role.strip() else None
        soul_text = str(soul).strip() if isinstance(soul, str) and soul.strip() else None
        inherit = (
            str(inherit_from).strip()
            if isinstance(inherit_from, str) and inherit_from.strip()
            else None
        )

        try:
            handle = self._catalog.create(
                CreateAssistantRequest(
                    name=name,
                    description=description,
                    template_id=template_id,
                    seed_user_md=seed or None,
                    from_role=role,
                    soul=soul_text,
                    inherit_from=inherit,
                )
            )
        except Exception as exc:  # catalog raises typed AssistantCatalogError
            return self._fail(start, f"创建失败: {exc}")

        profile = _read_profile(handle.home_path)
        emoji = str(profile.get("emoji") or "🤖")
        opening_message = str(profile.get("opening_message") or "")
        soul_summary = _read_text(handle.home_path, "SOUL.md")

        frontend_agent_id: str | None = None
        if self._bridge is not None:
            frontend_agent_id = await self._bridge.register(
                assistant_id=handle.assistant_id,
                name=name,
                description=description or str(profile.get("description", "")),
                emoji=emoji,
                system_role=soul_summary,
                opening_message=opening_message,
            )

        payload: dict[str, Any] = {
            "assistant_id": handle.assistant_id,
            "home_path": handle.home_path,
            "revision_seq": handle.revision_seq,
            "template_id": template_id,
            "name": name,
            "description": description,
            "emoji": emoji,
            "personality": _personality_from_soul(soul_summary),
            "tone": _tone_from_soul(soul_summary),
            "capabilities": _capabilities_from_home(handle.home_path),
            "bootstrap_completed": bool(seed or soul_text),
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
    """读 Home 的 profile.json（emoji/description/opening_message 回显用）；失败返回空。"""
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


def _soul_section(soul: str, marker: str) -> list[str]:
    """提取 SOUL 中某个 ``## `` 语义段的内容（去掉 ``- `` 前缀），段落到下一段截止。"""
    lines = soul.splitlines()
    items: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            if marker in line:
                in_section = True
                continue
            if in_section:
                break
        if in_section:
            stripped = line.strip().lstrip("- ").strip()
            if stripped:
                items.append(stripped)
    return items


def _personality_from_soul(soul: str) -> str:
    """从 SOUL 的「性格」段提取 1-3 句性格要点（ADR-0242 D7）。"""
    items = _soul_section(soul, "## 🎭 性格")
    return "；".join(items[:3])


def _tone_from_soul(soul: str) -> str:
    """从 SOUL 的「语气」段提取语气要点（ADR-0242 D7）。"""
    items = _soul_section(soul, "## 🗣 语气")
    return "；".join(items[:3])


def _capabilities_from_home(home_path: str) -> list[str]:
    """从 Home 推导能力清单：目标名 + 工具名 + 技能名（ADR-0242 D7）。

    角色卡创建时 goals.yaml 已含「核心使命」目标，模板创建时含模板示例目标；
    继承创建时 skills/ 含来源技能。
    """
    caps: list[str] = []
    caps.extend(_goal_names(home_path))
    caps.extend(_allowed_tool_names(home_path))
    caps.extend(_skill_names(home_path))

    seen: set[str] = set()
    result: list[str] = []
    for cap in caps:
        if cap and cap not in seen:
            seen.add(cap)
            result.append(cap)
    return result


def _goal_names(home_path: str) -> list[str]:
    """读 goals.yaml 的目标名列表；损坏 / 缺失返回空。"""
    try:
        data = yaml.safe_load((Path(home_path) / "goals.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    goals = data.get("goals") if isinstance(data, dict) else None
    if not isinstance(goals, list):
        return []
    return [
        str(goal.get("name")).strip()
        for goal in goals
        if isinstance(goal, dict) and goal.get("name")
    ]


def _allowed_tool_names(home_path: str) -> list[str]:
    """读 tools.yaml 的 allow 列表；损坏 / 缺失返回空。"""
    try:
        data = yaml.safe_load((Path(home_path) / "tools.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    tools = data.get("tools") if isinstance(data, dict) else None
    allow = tools.get("allow") if isinstance(tools, dict) else None
    if not isinstance(allow, list):
        return []
    return [str(tool).strip() for tool in allow if tool]


def _skill_names(home_path: str) -> list[str]:
    """列出 Home skills/ 下含 SKILL.md 的技能目录名。"""
    skills_dir = Path(home_path) / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        child.name
        for child in sorted(skills_dir.iterdir())
        if child.is_dir() and (child / "SKILL.md").is_file()
    ]


__all__ = ["CREATE_ASSISTANT_TOOL", "AssistantCreateTool"]
