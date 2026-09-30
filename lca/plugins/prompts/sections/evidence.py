"""Evidence-pack section."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import label_line
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


class EvidencePackSection:
    name: ClassVar[str] = "evidence_pack_text"

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
        from lca.contracts.models.team.consultation.consultation import build_evidence_pack_text

        outcomes = awareness.consult_duty.outcomes if awareness and awareness.consult_duty else ()
        text = build_evidence_pack_text(outcomes)
        return SectionOutput(
            text=label_line(
                "EVIDENCE_PACK（成员已返回的可综合证据；部分证据也算有效视角）",
                text,
            )
        )


def build_evidence_pack(config: BaseModel) -> EvidencePackSection:
    del config
    return EvidencePackSection()


__all__ = ["EvidencePackSection", "build_evidence_pack"]
