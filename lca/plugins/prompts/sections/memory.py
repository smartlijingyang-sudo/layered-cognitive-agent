"""Retrieval-duty and privacy-firewall prompt sections (ADR-0254 §5.1/§4.5).

These sections encode the mandatory retrieval decision tree, the terminal
anti-hallucination gate, and the cross-chat privacy firewall as model-visible
rules. The retrieval-duty section renders for every run (ADR-0260 section 6,
decision 2: the home-bound gate was a coverage omission, not intentional
design); runs without an assistant home get an explicit "no persistent memory
available" declaration instead of an empty block (fail-open by design). The
privacy firewall still renders only for home-bound runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.cognition.prompt_leak_markers import (
    MEMORY_WRITE_RULES_HEADER,
    UNRETRIEVED_LABEL,
)
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness

_RETRIEVAL_DUTY = (
    "## 记忆检索义务与决策树\n"
    "- 豁免: 纯寒暄、简短确认、逐字复制当轮材料、用户明确要求不查。\n"
    "- 实质请求先 memory_search（多角度，首个 query 贴近用户原话）；命中则 memory_explain 精读，未命中扫常驻文件兜底。\n"
    "- 易变事实复验（价格/档期/状态）行动前工具重验，记忆只给线索不给结论。\n"
    "- 检索落空：承认缺失并标注不确定性，绝不编造。\n"
    f'- {UNRETRIEVED_LABEL}: 本次未执行任何检索时，涉及记忆/事实的断言必须标注"未经检索"的不确定性，绝不编造。\n'
    "- 自省投影防幻觉: 自我认知以注入实体文件为准，不盲目探测。\n\n"
    f"{MEMORY_WRITE_RULES_HEADER}\n"
    '- 落笔前写盘: 收到写盘回执后，才可回复"记下了"；\n'
    "- 冲突原地修正（保留 provenance），不双写矛盾条目。\n"
    "- 凭证红线: 密码/Token/API Key 只记位置不记原文。\n\n"
    "## 表达分寸与声带契约（禁显摆）\n"
    '- 禁显摆套话: 严禁出现"我记得你说过……"、"正如您之前提到的……"、"据记忆库记录"等监控感/邀功式套话，直接结合上下文自然回答。\n'
    "- 敏感记忆分寸: 敏感事实（如健康隐患、家庭变故、财务压力等）非用户主动直接问及时严禁无故提及，绝不借旧账说教或当谈资。\n"
    "- 情绪承接优先: 面对沮丧或困难，优先真诚共情承接，切忌拿冷冰冰的旧记忆做说教式分析。\n\n"
    "## 思考经济性\n"
    "- 规则是约束不是解说词。思考对准目标，不复述规则条文；行动，不背诵。"
)

_PRIVACY_FIREWALL = (
    "## 跨会话隐私防火墙\n"
    "- 检索到不等于可透露。分支会话检索到主记忆或其他分支的内容时，不得向外泄露私密信息。\n"
    "- 本分支特有结论与未定决议写入 side-chats/<id>/MEMORY.md；"
    "跨会话的通用事实与用户偏好，先请用户确认再写入主记忆。"
)


_RETRIEVAL_DUTY_UNBOUND = (
    "## 记忆检索义务与决策树\n"
    "- 本次会话无持久记忆可用（未绑定 assistant home），不存在可检索的记忆源。\n"
    f'- {UNRETRIEVED_LABEL}: 涉及记忆/事实的断言必须标注"未经检索"的不确定性，绝不编造。\n'
)


class MemoryRetrievalSection:
    """Model-visible mandatory retrieval decision tree and terminal gate."""

    name: ClassVar[str] = "memory_retrieval"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: object,
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del task, awareness, manifest, tools, activated_skills
        if _has_home(role_profile):
            return SectionOutput(text=_RETRIEVAL_DUTY)
        return SectionOutput(text=_RETRIEVAL_DUTY_UNBOUND)


class PrivacyFirewallSection:
    """Model-visible "检索到 ≠ 可透露" firewall for side chats."""

    name: ClassVar[str] = "privacy_firewall"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: object,
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del task, awareness, manifest, tools, activated_skills
        if not _has_home(role_profile):
            return SectionOutput(text="")
        return SectionOutput(text=_PRIVACY_FIREWALL)


def _has_home(role_profile: RoleProfile) -> bool:
    extra = getattr(role_profile, "extra", {}) or {}
    return bool(str(extra.get("assistant_home_path") or "").strip())


def build_memory_retrieval(config: BaseModel) -> MemoryRetrievalSection:
    del config
    return MemoryRetrievalSection()


def build_privacy_firewall(config: BaseModel) -> PrivacyFirewallSection:
    del config
    return PrivacyFirewallSection()


__all__ = [
    "MemoryRetrievalSection",
    "PrivacyFirewallSection",
    "build_memory_retrieval",
    "build_privacy_firewall",
]
