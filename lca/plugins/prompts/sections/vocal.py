"""ADR-0248 vocal-contract section and its mutable prompt texts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import block
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.plugins.prompts.sections.base import _load_prompt_resource

# 默认文本来自资源文件；setup 时可按 instruction_overrides 覆盖。
_VOCAL_CONTRACT_TEXT = _load_prompt_resource("vocal_contract")
_REPLY_FIRST_TEXT = _load_prompt_resource("reply_first_reminder")


class VocalContractSection:
    """ADR-0248 声带契约段落：仅 gated 模式渲染（direct 返回空）。

    渲染规则：
    - ``vocal_mode != "gated"`` → 空输出（零侵入）；
    - gated：始终渲染声带契约（教模型唯一发声通道）；
    - 未 Ack 且 ``requires_reply_first`` → 追加 Reply-First 提醒。
    运行时状态经 ``current_bindings_view()`` 读取，不注入额外依赖。
    """

    name: ClassVar[str] = "vocal_contract"

    def __init__(self, contract_text: str, reminder_text: str) -> None:
        self._contract_text = contract_text
        self._reminder_text = reminder_text

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, awareness, manifest, tools, activated_skills
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
        )

        view = current_bindings_view()
        if view is None or getattr(view, "vocal_mode", "direct") != "gated":
            return SectionOutput(text="")

        parts = [self._contract_text]
        gate = getattr(view, "vocal_gate", None)
        if gate is not None:
            wake = getattr(gate, "wake_context", None)
            requires_reply_first = bool(getattr(wake, "requires_reply_first", False))
            has_acked = bool(getattr(gate, "has_acked", False))
            if requires_reply_first and not has_acked:
                parts.append(self._reminder_text)
        return SectionOutput(text=block("vocal_contract", "\n\n".join(parts)))


def build_vocal_contract(config: BaseModel) -> VocalContractSection:
    """ADR-0248 声带契约段落构造器（文本经 instruction_overrides 覆盖）。"""
    del config
    return VocalContractSection(_VOCAL_CONTRACT_TEXT, _REPLY_FIRST_TEXT)


__all__ = ["VocalContractSection", "build_vocal_contract"]
