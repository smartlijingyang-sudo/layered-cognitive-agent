"""Assistant self-management tools (ADR-0242 D6).

A governed tool family that lets the assistant inspect and modify its own
Home.  All writes go through the single configuration write-entry
``AssistantCatalog.revise_profile`` or the skill overlay's ``remove`` — no
tool writes Home files directly (I-B6).

Approval semantics (I-B7): sensitive operations (delete skill, expand
grants) require an explicit ``confirmed: true`` argument, which the LLM only
sets after the user confirms via ``askUserQuestion``.  Non-sensitive changes
apply and return a payload the LLM relays to the user ("改完告知").
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.assistant.tool_spec import ToolSpec
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.assistant.catalog import ProfilePatch
from lca.infrastructure.observability.facade.run.ambit import current_assistant_id

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.catalog import AssistantCatalog
    from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay
    from lca.contracts.protocols.assistant.tool_overlay import AssistantToolOverlay

_LIST_ASSISTANT_SKILLS_TOOL = "list_assistant_skills"
_DELETE_ASSISTANT_SKILL_TOOL = "delete_assistant_skill"
_EDIT_ASSISTANT_SKILL_TOOL = "edit_assistant_skill"
_UPDATE_ASSISTANT_SOUL_TOOL = "update_assistant_soul"
_UPDATE_ASSISTANT_PROFILE_TOOL = "update_assistant_profile"
_UPDATE_ASSISTANT_GRANTS_TOOL = "update_assistant_grants"
_LIST_ASSISTANT_TOOLS_TOOL = "list_assistant_tools"
_CREATE_ASSISTANT_TOOL_TOOL = "create_assistant_tool"
_UPDATE_ASSISTANT_TOOL_TOOL = "update_assistant_tool"
_DELETE_ASSISTANT_TOOL_TOOL = "delete_assistant_tool"

_SENSITIVE_CONFIRMATION_HINT = (
    "这是敏感操作，必须先经用户确认：调用 askUserQuestion 询问用户是否确认，"
    "用户明确同意后才可携带 confirmed=true 再次调用。"
)


class _BaseAssistantTool(Tool):
    """Shared scaffolding for the assistant self-management tools."""

    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        assistant_id: str,
        overlay: AssistantSkillOverlay | None = None,
        tool_overlay: AssistantToolOverlay | None = None,
        catalog_names: Callable[[], list[str]] | None = None,
    ) -> None:
        self._catalog = catalog
        self._assistant_id = assistant_id
        self._overlay = overlay
        self._tool_overlay = tool_overlay
        self._catalog_names = catalog_names

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


class ListAssistantSkillsTool(_BaseAssistantTool):
    """List the skills installed in the bound assistant's Home (read-only)."""

    name = _LIST_ASSISTANT_SKILLS_TOOL
    description = "列出当前助理 Home 已安装的技能（skill_id 列表）。只读，不修改任何配置。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        start = time.monotonic()
        if self._overlay is None:
            return self._fail(start, "assistant.skill_overlay 能力不可用")
        from lca.infrastructure.tools.assistant.create_skill_tool import (
            CREATE_ASSISTANT_SKILL_TOOL,
        )

        try:
            receipts = self._overlay.list_installed(self._assistant_id)
        except Exception as exc:
            return self._fail(start, f"读取技能失败: {exc}")
        skills = [
            {"skill_id": r.skill_id, "state": r.artifact_state, "path": r.install_path}
            for r in receipts
        ]
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "skills": skills,
                "hint": (
                    f"可用 create_assistant_skill（{CREATE_ASSISTANT_SKILL_TOOL}）安装新技能，"
                    f"用 delete_assistant_skill 删除（敏感，需用户确认）。"
                ),
            },
        )


class DeleteAssistantSkillTool(_BaseAssistantTool):
    """Delete a skill from the assistant's Home (sensitive, requires confirmation)."""

    name = _DELETE_ASSISTANT_SKILL_TOOL
    description = (
        "删除当前助理 Home 的一个已安装技能（不可逆，敏感操作）。"
        "必须先经用户确认：调用 askUserQuestion 询问，用户同意后才携带 confirmed=true 调用。"
        "参数: skill_id（要删除的技能 id）、confirmed（用户是否已确认，必须为 true）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "要删除的技能 id"},
            "confirmed": {
                "type": "boolean",
                "description": "用户是否已明确确认删除（敏感操作必须为 true）",
            },
        },
        "required": ["skill_id", "confirmed"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        skill_id = str(args.get("skill_id") or "").strip()
        if not skill_id:
            return self._fail(start, "skill_id 必须为非空字符串")
        if args.get("confirmed") is not True:
            return self._fail(start, f"删除技能需要用户确认。{_SENSITIVE_CONFIRMATION_HINT}")
        if self._overlay is None:
            return self._fail(start, "assistant.skill_overlay 能力不可用")

        try:
            await self._overlay.remove(self._assistant_id, skill_id, actor="agent")
        except Exception as exc:
            return self._fail(start, f"删除技能失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "deleted_skill_id": skill_id,
                "message": f"已删除技能「{skill_id}」。",
            },
        )


class EditAssistantSkillTool(_BaseAssistantTool):
    """Edit a skill in the assistant's Home (COW, non-sensitive)."""

    name = _EDIT_ASSISTANT_SKILL_TOOL
    description = (
        "编辑当前助理 Home 的一个已安装技能（写时复制：若该技能链接自全局库，"
        "会先复制为助理私有副本再修改，不影响其他 agent）。非敏感操作，改完告知用户。"
        "参数: skill_id（要编辑的技能 id）、skill_md（新的 SKILL.md 全文，含 YAML frontmatter）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "要编辑的技能 id"},
            "skill_md": {
                "type": "string",
                "description": "新的 SKILL.md 全文（含 YAML frontmatter）",
            },
        },
        "required": ["skill_id", "skill_md"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        skill_id = str(args.get("skill_id") or "").strip()
        skill_md = str(args.get("skill_md") or "").strip()
        if not skill_id:
            return self._fail(start, "skill_id 必须为非空字符串")
        if not skill_md:
            return self._fail(start, "skill_md 必须为非空字符串")
        if self._overlay is None:
            return self._fail(start, "assistant.skill_overlay 能力不可用")
        try:
            receipt = await self._overlay.edit(
                self._assistant_id, skill_id, skill_md, actor="agent"
            )
        except Exception as exc:
            return self._fail(start, f"编辑技能失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "skill_id": receipt.skill_id,
                "source": receipt.source,
                "path": receipt.install_path,
                "message": f"已编辑技能「{receipt.skill_id}」。",
            },
        )


class UpdateAssistantSoulTool(_BaseAssistantTool):
    """Update the assistant's SOUL.md (non-sensitive, notify after applying)."""

    name = _UPDATE_ASSISTANT_SOUL_TOOL
    description = (
        "修改当前助理的 SOUL.md（人格/语气/边界）。非敏感操作，改完告知用户。"
        "SOUL 必须包含四个核心语义段（## 🧠 身份 / ## 🎭 性格 / ## 🛠 能力 / ## 🗣 语气），"
        "去除空白后至少 200 字符。参数: soul（新的 SOUL 全文）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "soul": {"type": "string", "description": "新的 SOUL.md 全文（Markdown）"},
        },
        "required": ["soul"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        soul = str(args.get("soul") or "").strip()
        if not soul:
            return self._fail(start, "soul 必须为非空字符串")
        try:
            revision = self._catalog.revise_profile(
                self._assistant_id,
                ProfilePatch(soul_md=soul),
                actor="agent",
            )
        except Exception as exc:
            return self._fail(start, f"更新 SOUL 失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "revision_seq": revision.revision_seq,
                "message": "已更新 SOUL.md（人格/语气/边界）。",
            },
        )


class UpdateAssistantProfileTool(_BaseAssistantTool):
    """Update the assistant's profile.json name/description (non-sensitive)."""

    name = _UPDATE_ASSISTANT_PROFILE_TOOL
    description = (
        "修改当前助理的 profile（名字 / 描述 / emoji 通过描述体现）。非敏感操作，改完告知用户。"
        "参数: name（可选，新名字）、description（可选，新职责描述）。至少提供一个。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "新的助理名字"},
            "description": {"type": "string", "description": "新的一句话职责描述"},
        },
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        name = str(args.get("name") or "").strip()
        description = str(args.get("description") or "").strip()
        if not name and not description:
            return self._fail(start, "name 与 description 至少提供一个")
        try:
            revision = self._catalog.revise_profile(
                self._assistant_id,
                ProfilePatch(
                    profile_name=name or None,
                    profile_description=description or None,
                ),
                actor="agent",
            )
        except Exception as exc:
            return self._fail(start, f"更新 profile 失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "revision_seq": revision.revision_seq,
                "message": "已更新助理 profile（名字/描述）。",
            },
        )


class UpdateAssistantGrantsTool(_BaseAssistantTool):
    """Update the assistant's grants.yaml (sensitive, requires confirmation)."""

    name = _UPDATE_ASSISTANT_GRANTS_TOOL
    description = (
        "修改当前助理的 grants.yaml（能力授权，扩权敏感）。"
        "必须先经用户确认：调用 askUserQuestion 询问，用户同意后才携带 confirmed=true 调用。"
        "参数: grants_yaml（新的 grants.yaml 全文）、confirmed（用户是否已确认，必须为 true）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "grants_yaml": {"type": "string", "description": "新的 grants.yaml 全文"},
            "confirmed": {
                "type": "boolean",
                "description": "用户是否已明确确认（扩权敏感操作必须为 true）",
            },
        },
        "required": ["grants_yaml", "confirmed"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        grants_yaml = str(args.get("grants_yaml") or "").strip()
        if not grants_yaml:
            return self._fail(start, "grants_yaml 必须为非空字符串")
        if args.get("confirmed") is not True:
            return self._fail(start, f"修改授权需要用户确认。{_SENSITIVE_CONFIRMATION_HINT}")
        try:
            revision = self._catalog.revise_profile(
                self._assistant_id,
                ProfilePatch(grants_yaml=grants_yaml),
                actor="agent",
            )
        except Exception as exc:
            return self._fail(start, f"更新 grants 失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "revision_seq": revision.revision_seq,
                "message": "已更新 grants.yaml（能力授权）。",
            },
        )


class ListAssistantToolsTool(_BaseAssistantTool):
    """List the assistant's effective tool set: builtin policy + custom tools."""

    name = _LIST_ASSISTANT_TOOLS_TOOL
    description = (
        "列出当前助理的工具集：内置工具的 allow/deny 策略 + 自定义工具详情。"
        "只读，不修改任何配置。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        start = time.monotonic()
        try:
            spec = self._catalog.get(self._assistant_id)
            tools_path = Path(spec.home_path) / "tools.yaml"
            import yaml

            data = yaml.safe_load(tools_path.read_text(encoding="utf-8")) or {}
            tools = data.get("tools") if isinstance(data, dict) else {}
            allow = tools.get("allow") if isinstance(tools, dict) else []
            deny = tools.get("deny") if isinstance(tools, dict) else []
            grants = self._load_grants(Path(spec.home_path))

            custom_tools: list[dict[str, object]] = []
            if self._tool_overlay is not None:
                for receipt in self._tool_overlay.list_installed(self._assistant_id):
                    custom_tools.append(
                        {
                            "tool_id": receipt.tool_id,
                            "path": receipt.install_path,
                            "digest": receipt.digest,
                        }
                    )

            catalog = sorted(self._catalog_names()) if self._catalog_names else []
            allowed_builtins = [
                name for name in catalog if name not in deny and (not allow or name in allow)
            ]
        except Exception as exc:
            return self._fail(start, f"读取工具失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "allow": list(allow) if isinstance(allow, list) else [],
                "deny": list(deny) if isinstance(deny, list) else [],
                "grants": sorted(grants),
                "builtin_catalog": catalog,
                "allowed_builtins": allowed_builtins,
                "custom_tools": custom_tools,
                "hint": (
                    "可用 create_assistant_tool（写 {home}/tools/<id>/tool.json）新增自定义工具，"
                    "用 update_assistant_tool 修改，delete_assistant_tool 删除（敏感，需用户确认）。"
                ),
            },
        )

    def _load_grants(self, home: Path) -> frozenset[str]:
        import yaml

        path = home / "grants.yaml"
        if not path.is_file():
            return frozenset()
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return frozenset()
        if not isinstance(parsed, dict):
            return frozenset()
        grants = parsed.get("grants")
        if not isinstance(grants, list):
            return frozenset()
        return frozenset(str(g).strip() for g in grants if isinstance(g, str) and g.strip())


class CreateAssistantToolTool(_BaseAssistantTool):
    """Create a custom tool in the assistant's Home (ADR-0243 D6)."""

    name = _CREATE_ASSISTANT_TOOL_TOOL
    description = (
        "为当前助理新增一个自定义工具，写入 Home 的 tools/ 目录。"
        "参数: tool_json（tool.json 全文，含 name/description/parameters/handler）。"
        "非敏感操作，改完告知用户。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "tool_json": {
                "type": "string",
                "description": "tool.json 全文（JSON），schema 见 ToolSpec",
            },
        },
        "required": ["tool_json"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        raw = str(args.get("tool_json") or "").strip()
        if not raw:
            return self._fail(start, "tool_json 必须为非空字符串")
        if self._tool_overlay is None:
            return self._fail(start, "assistant.tool_overlay 能力不可用")
        try:
            spec = ToolSpec.model_validate_json(raw)
            receipt = await self._tool_overlay.create(self._assistant_id, spec, actor="agent")
        except Exception as exc:
            return self._fail(start, f"新增工具失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "tool_id": receipt.tool_id,
                "path": receipt.install_path,
                "message": f"已新增自定义工具「{receipt.tool_id}」。",
            },
        )


class UpdateAssistantToolTool(_BaseAssistantTool):
    """Update a custom tool in the assistant's Home (ADR-0243 D6)."""

    name = _UPDATE_ASSISTANT_TOOL_TOOL
    description = (
        "修改当前助理的一个自定义工具。"
        "参数: tool_id（要修改的工具 id，与 tool_json.name 一致）、tool_json（新的全文）。"
        "非敏感操作，改完告知用户。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "tool_id": {"type": "string", "description": "要修改的工具 id"},
            "tool_json": {"type": "string", "description": "新的 tool.json 全文"},
        },
        "required": ["tool_id", "tool_json"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        tool_id = str(args.get("tool_id") or "").strip()
        raw = str(args.get("tool_json") or "").strip()
        if not tool_id:
            return self._fail(start, "tool_id 必须为非空字符串")
        if not raw:
            return self._fail(start, "tool_json 必须为非空字符串")
        if self._tool_overlay is None:
            return self._fail(start, "assistant.tool_overlay 能力不可用")
        try:
            spec = ToolSpec.model_validate_json(raw)
            receipt = await self._tool_overlay.update(
                self._assistant_id, tool_id, spec, actor="agent"
            )
        except Exception as exc:
            return self._fail(start, f"修改工具失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "tool_id": receipt.tool_id,
                "path": receipt.install_path,
                "message": f"已修改自定义工具「{receipt.tool_id}」。",
            },
        )


class DeleteAssistantToolTool(_BaseAssistantTool):
    """Delete a custom tool from the assistant's Home (sensitive)."""

    name = _DELETE_ASSISTANT_TOOL_TOOL
    description = (
        "删除当前助理的一个自定义工具（不可逆，敏感操作）。"
        "必须先经用户确认：调用 askUserQuestion 询问，用户同意后才携带 confirmed=true 调用。"
        "参数: tool_id（要删除的工具 id）、confirmed（用户是否已确认，必须为 true）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "tool_id": {"type": "string", "description": "要删除的工具 id"},
            "confirmed": {
                "type": "boolean",
                "description": "用户是否已明确确认删除（敏感操作必须为 true）",
            },
        },
        "required": ["tool_id", "confirmed"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        tool_id = str(args.get("tool_id") or "").strip()
        if not tool_id:
            return self._fail(start, "tool_id 必须为非空字符串")
        if args.get("confirmed") is not True:
            return self._fail(start, f"删除工具需要用户确认。{_SENSITIVE_CONFIRMATION_HINT}")
        if self._tool_overlay is None:
            return self._fail(start, "assistant.tool_overlay 能力不可用")
        try:
            await self._tool_overlay.remove(self._assistant_id, tool_id, actor="agent")
        except Exception as exc:
            return self._fail(start, f"删除工具失败: {exc}")
        return self._ok(
            start,
            {
                "assistant_id": self._assistant_id,
                "deleted_tool_id": tool_id,
                "message": f"已删除自定义工具「{tool_id}」。",
            },
        )


def assistant_self_manage_tools_from_run(
    run: object | None,
    *,
    catalog: AssistantCatalog,
    overlay: AssistantSkillOverlay | None = None,
    tool_overlay: AssistantToolOverlay | None = None,
    catalog_names: Callable[[], list[str]] | None = None,
) -> list[Tool]:
    """Materialize the self-management tools when the run binds an assistant_id."""
    bind = run if isinstance(run, dict) else {}
    explicit = str(bind.get("assistant_id") or "").strip()
    assistant_id = explicit or current_assistant_id().strip()
    if not assistant_id:
        return []
    return [
        ListAssistantSkillsTool(catalog=catalog, assistant_id=assistant_id, overlay=overlay),
        DeleteAssistantSkillTool(catalog=catalog, assistant_id=assistant_id, overlay=overlay),
        EditAssistantSkillTool(catalog=catalog, assistant_id=assistant_id, overlay=overlay),
        UpdateAssistantSoulTool(catalog=catalog, assistant_id=assistant_id),
        UpdateAssistantProfileTool(catalog=catalog, assistant_id=assistant_id),
        UpdateAssistantGrantsTool(catalog=catalog, assistant_id=assistant_id),
        ListAssistantToolsTool(
            catalog=catalog,
            assistant_id=assistant_id,
            tool_overlay=tool_overlay,
            catalog_names=catalog_names,
        ),
        CreateAssistantToolTool(
            catalog=catalog, assistant_id=assistant_id, tool_overlay=tool_overlay
        ),
        UpdateAssistantToolTool(
            catalog=catalog, assistant_id=assistant_id, tool_overlay=tool_overlay
        ),
        DeleteAssistantToolTool(
            catalog=catalog, assistant_id=assistant_id, tool_overlay=tool_overlay
        ),
    ]


__all__ = [
    "_CREATE_ASSISTANT_TOOL_TOOL",
    "_DELETE_ASSISTANT_SKILL_TOOL",
    "_DELETE_ASSISTANT_TOOL_TOOL",
    "_EDIT_ASSISTANT_SKILL_TOOL",
    "_LIST_ASSISTANT_SKILLS_TOOL",
    "_LIST_ASSISTANT_TOOLS_TOOL",
    "_UPDATE_ASSISTANT_GRANTS_TOOL",
    "_UPDATE_ASSISTANT_PROFILE_TOOL",
    "_UPDATE_ASSISTANT_SOUL_TOOL",
    "_UPDATE_ASSISTANT_TOOL_TOOL",
    "CreateAssistantToolTool",
    "DeleteAssistantSkillTool",
    "DeleteAssistantToolTool",
    "EditAssistantSkillTool",
    "ListAssistantSkillsTool",
    "ListAssistantToolsTool",
    "UpdateAssistantGrantsTool",
    "UpdateAssistantProfileTool",
    "UpdateAssistantSoulTool",
    "UpdateAssistantToolTool",
    "assistant_self_manage_tools_from_run",
]
