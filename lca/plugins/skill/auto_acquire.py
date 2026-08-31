"""Candidate-only procedural-skill acquisition plugin.

This first implementation deliberately does not write to the installed skill
store.  It converts sufficiently evidenced successful episodes into immutable
drafts; a separately evaluated and approved promotion path must materialize any
candidate as a reusable skill package.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import LEARNING_SKILL_ACQUIRER
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.learning import SkillAcquirer, SkillAcquisitionCandidate
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class AutoAcquireSkillService(SkillAcquirer):
    """Create skill candidates only when configured evidence gates are met."""

    enabled: bool
    min_confidence: float
    min_evidence: int

    def propose(
        self,
        *,
        task_ref: str,
        procedure: str,
        success: bool,
        confidence: float,
        evidence_refs: tuple[str, ...],
    ) -> SkillAcquisitionCandidate | None:
        """Return a draft candidate or ``None`` without changing any skill store."""

        if (
            not self.enabled
            or not success
            or not task_ref.strip()
            or not procedure.strip()
            or confidence < self.min_confidence
            or len(evidence_refs) < self.min_evidence
        ):
            return None
        digest = sha256(f"{task_ref}\0{procedure}\0{'|'.join(evidence_refs)}".encode()).hexdigest()[
            :16
        ]
        return SkillAcquisitionCandidate(
            candidate_id=f"skill-candidate-{digest}",
            task_ref=task_ref,
            procedure=procedure,
            confidence=confidence,
            evidence_refs=tuple(evidence_refs),
        )


class Config(BaseModel):
    """Evidence gates declared by the owning learning scenario bundle."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    min_evidence: int = Field(default=3, ge=1)


@plugin(
    id="lca-skill-auto-acquire",
    provides=[LEARNING_SKILL_ACQUIRER.key],
    requires=[],
    implements=[SkillAcquirer],
    layer="L1",
    effects="none",
    description="Produce evidence-gated procedural-skill candidates without auto-promotion.",
    test_suite="tests/architecture/test_self_improving_plugins.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G11_CREATION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G11_CREATION,
        control_slot=ControlSlot.OBSERVE_CHECKPOINT,
        scope=Scope.RUN,
        authority=(LEARNING_SKILL_ACQUIRER.key, "evidence.read"),
        evidence=("learning.skill-candidate.proposed",),
        revision="v1",
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the candidate generator selected by this scenario profile."""

    ctx.provide(
        LEARNING_SKILL_ACQUIRER.key,
        AutoAcquireSkillService(
            enabled=config.enabled,
            min_confidence=config.min_confidence,
            min_evidence=config.min_evidence,
        ),
    )


__all__ = ["AutoAcquireSkillService", "Config", "SkillAcquisitionCandidate"]
