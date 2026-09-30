"""Retrieval-duty and privacy-firewall prompt sections (ADR-0254 §5.1/§4.5).

These sections encode the mandatory retrieval decision tree, the terminal
anti-hallucination gate, and the cross-chat privacy firewall as model-visible
rules. They render only when the run is bound to an assistant home so
unbound runs keep their prompt unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness

_RETRIEVAL_DUTY = (
    "## 记忆检索义务\n"
    "- 豁免: 纯寒暄、简短无实质确认、逐字复制当轮材料。\n"
    "- 其余实质请求必须先调用 memory_search 发起多角度查询（至少 3 个角度），"
    "命中后用 memory_explain 精读，未命中时扫描常驻记忆文件兜底。\n"
    "- 防幻觉终端闸门: 检索仍然落空时，基于已有已知上下文作答，明确承认信息缺失"
    "并标注不确定性，绝不凭空编造事实。"
)

_PRIVACY_FIREWALL = (
    "## 跨会话隐私防火墙\n"
    "- 检索到不等于可透露。分支会话检索到主记忆或其他分支的内容时，不得向外泄露私密信息。\n"
    "- 本分支特有结论与未定决议写入 side-chats/<id>/MEMORY.md；"
    "跨会话的通用事实与用户偏好，先请用户确认再写入主记忆。"
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
        if not _has_home(role_profile):
            return SectionOutput(text="")
        return SectionOutput(text=_RETRIEVAL_DUTY)


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
