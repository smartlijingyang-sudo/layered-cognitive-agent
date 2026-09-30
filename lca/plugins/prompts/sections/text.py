"""Static instruction-block sections and their baked-in texts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.plugins.prompts.sections.base import (
    StaticTextSection,
    _load_prompt_resource,
    build_static_text,
)


class ReactWorkflowSection(StaticTextSection):
    name = "react_workflow"


@dataclass
class ReactToolUsageSection(StaticTextSection):
    """工具使用指南。gated 模式返回去掉「文本直出」冲突指令的变体。"""

    name: ClassVar[str] = "react_tool_usage_guidelines"
    gated_text: str = ""

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
        )

        view = current_bindings_view()
        if view is not None and getattr(view, "vocal_mode", "direct") == "gated":
            return SectionOutput(text=self.gated_text)
        return SectionOutput(text=self.text)


class RoutingInstructionsSection(StaticTextSection):
    name = "routing_instructions"


class HierarchicalInstructionsSection(StaticTextSection):
    name = "hierarchical_instructions"


# ── Profile-driven text blocks (must live here, not in modules/types) ─────
# The static instruction blocks are content policy owned by the profile,
# but the section surface is owned by the L1 primitive. Profiles can override
# these via plugin config when more than the built-in is needed.

_REACT_WORKFLOW_TEXT = """<workflow>
1. Understand the user's request.
2. Select the appropriate tool(s) for the task.
3. Execute operations.
4. Present results clearly.
5. Export files by default when the user asks to create/generate/save something.
</workflow>"""

# ADR-0248 gated 变体：移除「文本直出」冲突指令，正文来自资源文件。
_REACT_TOOL_USAGE_TEXT_GATED = _load_prompt_resource("react_tool_usage_guidelines_gated")

_REACT_TOOL_USAGE_TEXT = """<tool_usage_guidelines>
- Tools in <tools> are called via function calling (native tool_calls)
- Skills in <available_skills> require activate_skill first; <activated_skills> are already active
- Each step: one LLM call only — text and tool_calls belong to the same completion
- When tools are needed: use function calling (native tool_calls), do not output text then call tools separately
- When no tools are needed: reply with text directly (pure text response ends the step)
- Freshness & Real-time Search: Consult CURRENT_DATE. Whenever knowledge may have evolved after training cutoff (breaking news, current year status, latest versions, changelogs, live APIs), prioritize calling web_search over parametric memory. Follow search routing guidelines.
- Reply in standard Markdown format
- If a previous tool call was rejected by the gate or returned an empty/error result, do not repeat the same invocation. Instead, produce a plain-text answer explaining what went wrong and stop.
- writeFile lands text in the sandbox (large files are chunked there). Put path before content. For generating PDF/xlsx from files already in the workspace, prefer executeCode so the artifact is created in-sandbox instead of inlining the dataset into a script.
- Do not pip install packages listed as pre-installed (reportlab, openpyxl, pandas, python-docx, pypdf). Use them directly.
- PDF Chinese text: use reportlab's built-in STSong-Light CID font; do not fc-list or download fonts.
- matplotlib CJK is preconfigured; do not set font.sans-serif; do not fc-list.
</tool_usage_guidelines>"""

_ROUTING_INSTRUCTIONS_TEXT = """你是团队主导者（lead，自由路由模式）。

## 工作规则
1. 根据任务动态决定是否需要队友、需要谁、如何表述子任务——不必咨询全部角色。
2. MEMBER_REPORTS 中列出的每一条，就是对应委派**已经返回**的结果——它们是你的事实来源，
   不是需要重新触发的历史记录。信息足够时直接文字回复综合结论；不要为了"走完流程"而委派。
3. 严禁重复委派 MEMBER_REPORTS 中已有返回的相同（角色, 子任务）。只有当某次委派标记为失败、
   或你确实需要同一角色补充新内容时，才可再次委派该角色，且必须更换子任务表述并说明原因。
4. 自己动手时：<tools> 中的工具通过 function calling 调用；<activated_skills> 已激活可直接执行；
   <available_skills> 需先 activate_skill 加载指南。

## 委派
若 <tools> 中配置了委派工具（如 delegate 或 handoff_to_peer），需要队友协助时通过原生 function calling 调用。可以一次委派多个角色（并行），也可以单目标委派。
若未配置委派工具，请基于现有上下文与自身能力直接综合分析并给出最终回复；严禁在正文中臆造或输出伪 XML 标签（如 <tool>、<delegate_to> 等）或虚构工具调用。

## 输出规则
- 需要调用工具时，使用 function calling（原生 tool_calls）
- 不需要工具时，直接用文字回复用户
- 回复使用标准 Markdown 格式"""

_HIERARCHICAL_INSTRUCTIONS_TEXT = """你是团队主导者（lead）。

## 工作规则
1. 每一轮先审视 EVIDENCE_PACK 与 CONTEXT 中已有的委派结果，判断哪些队友尚未提供**可用**输入。
2. 若 MEMBER_STATUS 仍显示待咨询角色，且框架未自动委派，可 delegate 给尚未发言的队友。
3. 当所有角色已终态（完整证据 / 部分证据 / 失败）后，直接文字回复综合；**必须优先吸收 EVIDENCE_PACK**，不得假装未见。
4. 禁止把同一个子任务反复委派给同一角色——每个角色最多有效咨询一次；部分证据也算已覆盖该视角。
5. 若部分角色失败且无证据，在回复中明确标注缺失视角并给出 lead 兜底，勿空转重试。
6. 自己动手时：<tools> 中的工具通过 function calling 调用；<activated_skills> 已激活可直接执行；
   <available_skills> 需先 activate_skill 加载指南。

## 委派
若 <tools> 中配置了委派工具（如 delegate 或 handoff_to_peer），需要队友协助时通过原生 function calling 调用，说明 target_role 和 subtask。
若未配置委派工具，请基于现有上下文与自身能力直接综合分析并给出最终回复；严禁在正文中臆造或输出伪 XML 标签（如 <tool>、<delegate_to> 等）或虚构工具调用。

## 输出规则
- 需要调用工具时，使用 function calling（原生 tool_calls）
- 不需要工具时，直接用文字回复用户
- 回复使用标准 Markdown 格式"""


def build_react_workflow(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "react_workflow", _REACT_WORKFLOW_TEXT)


def build_react_tool_usage(config: BaseModel) -> ReactToolUsageSection:
    text = getattr(config, "text", None) or _REACT_TOOL_USAGE_TEXT
    gated_text = getattr(config, "gated_text", None) or _REACT_TOOL_USAGE_TEXT_GATED
    return ReactToolUsageSection(text=text, gated_text=gated_text)


def build_routing_instructions(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "routing_instructions", _ROUTING_INSTRUCTIONS_TEXT)


def build_hierarchical_instructions(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "hierarchical_instructions", _HIERARCHICAL_INSTRUCTIONS_TEXT)


__all__ = [
    "HierarchicalInstructionsSection",
    "ReactToolUsageSection",
    "ReactWorkflowSection",
    "RoutingInstructionsSection",
    "build_hierarchical_instructions",
    "build_react_tool_usage",
    "build_react_workflow",
    "build_routing_instructions",
]
