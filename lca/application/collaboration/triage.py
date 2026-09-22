"""Coordinator triage router for multi-agent collaboration.

Implements the single-entrypoint convergence principle:
- Default to SOLO (never spam peers unnecessarily)
- Explicit specialist mentions route to PEER_HANDOFF
- Complex architectural and system-level objectives route to TEAM_CAST (Architecture Triad)
- Generates typed HandoffEnvelopes with clean context slices (anti-pollution)
"""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.collaboration.peer import HandoffEnvelope

_ARCH_TRIAD = (
    "architecture/guanlan",
    "architecture/hengyue",
    "architecture/jingchuan",
)

_ARCH_KEYWORDS = frozenset(
    {
        "架构",
        "契约",
        "不变量",
        "状态机",
        "重构",
        "审计",
        "反模式",
        "分层",
        "seam",
        "边界",
        "adr",
    }
)


class TriageDecisionKind(StrEnum):
    """Routing classification for coordinator triage."""

    SOLO = "solo"
    SUBAGENT = "subagent"
    PEER_HANDOFF = "peer_handoff"
    TEAM_CAST = "team_cast"


class TriageDecision(BaseModel):
    """Result of coordinator triage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TriageDecisionKind
    selected_peers: tuple[str, ...] = ()
    reasoning: str
    envelopes: tuple[HandoffEnvelope, ...] = ()


class CoordinatorTriageRouter:
    """Evaluates user objectives to determine collaboration topology."""

    def __init__(self, triad: tuple[str, ...] = _ARCH_TRIAD) -> None:
        self._triad = triad

    def triage(
        self,
        objective: str,
        correlation_id: str | None = None,
        sender_id: str = "coordinator_sam",
        context_extra: dict[str, Any] | None = None,
    ) -> TriageDecision:
        cid = correlation_id or f"run_{uuid.uuid4().hex[:12]}"
        lowered = objective.lower()

        # 1. 单点专家明确点名 / 显式 Hand-off
        if "观澜" in objective:
            target = "architecture/guanlan"
            envelope = self._build_envelope(cid, sender_id, target, objective, context_extra)
            return TriageDecision(
                kind=TriageDecisionKind.PEER_HANDOFF,
                selected_peers=(target,),
                reasoning="显式指定架构边界与契约总监：观澜",
                envelopes=(envelope,),
            )
        if "衡岳" in objective:
            target = "architecture/hengyue"
            envelope = self._build_envelope(cid, sender_id, target, objective, context_extra)
            return TriageDecision(
                kind=TriageDecisionKind.PEER_HANDOFF,
                selected_peers=(target,),
                reasoning="显式指定状态机与不变量总监：衡岳",
                envelopes=(envelope,),
            )
        if "镜川" in objective:
            target = "architecture/jingchuan"
            envelope = self._build_envelope(cid, sender_id, target, objective, context_extra)
            return TriageDecision(
                kind=TriageDecisionKind.PEER_HANDOFF,
                selected_peers=(target,),
                reasoning="显式指定对抗审查与反模式审计师：镜川",
                envelopes=(envelope,),
            )

        # 2. 复合架构与系统演化任务 -> 架构三角自动组队 (TEAM_CAST)
        hit_keywords = [kw for kw in _ARCH_KEYWORDS if kw in lowered]
        if len(hit_keywords) >= 2 or any(kw in lowered for kw in ("重构", "架构", "不变量")):
            envelopes = tuple(
                self._build_envelope(cid, sender_id, peer_id, objective, context_extra)
                for peer_id in self._triad
            )
            return TriageDecision(
                kind=TriageDecisionKind.TEAM_CAST,
                selected_peers=self._triad,
                reasoning=f"识别为复合系统架构议题（命中: {', '.join(hit_keywords)}），激活架构三角协同",
                envelopes=envelopes,
            )

        # 3. 默认单人收敛 (SOLO)
        return TriageDecision(
            kind=TriageDecisionKind.SOLO,
            selected_peers=(),
            reasoning="常规单步任务，协调者自行处理闭环",
            envelopes=(),
        )

    def _build_envelope(
        self,
        correlation_id: str,
        sender_id: str,
        receiver_id: str,
        objective: str,
        context_extra: dict[str, Any] | None,
    ) -> HandoffEnvelope:
        context_slice = {"topic": "architecture_collaboration"}
        if context_extra:
            context_slice.update(context_extra)

        return HandoffEnvelope(
            correlation_id=correlation_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            intent="delegate",
            objective=objective,
            context_slice=context_slice,
        )
