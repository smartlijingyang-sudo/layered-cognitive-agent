"""Coordinator triage router for multi-agent collaboration.

Implements the single-entrypoint convergence principle:
- Default to SOLO (never spam peers unnecessarily)
- Explicit specialist mentions route to PEER_HANDOFF (dynamically matched from candidates/library)
- Complex architectural and system-level objectives route to TEAM_CAST
- Generates typed HandoffEnvelopes with clean context slices (anti-pollution)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.collaboration.peer import HandoffEnvelope, PeerProfile

_logger = logging.getLogger(__name__)

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
    """Evaluates user objectives to determine collaboration topology without hardcoded roles."""

    def __init__(
        self,
        candidates: Sequence[PeerProfile] | None = None,
        default_team: Sequence[str] | None = None,
        role_library: Any | None = None,
    ) -> None:
        self._candidates = tuple(candidates) if candidates else ()
        self._default_team = tuple(default_team) if default_team else None
        self._role_library = role_library

    def triage(
        self,
        objective: str,
        correlation_id: str | None = None,
        sender_id: str = "coordinator_agent",
        context_extra: dict[str, Any] | None = None,
    ) -> TriageDecision:
        cid = correlation_id or f"run_{uuid.uuid4().hex[:12]}"
        lowered = objective.lower()

        # 1. 单点专家明确点名 / 显式 Hand-off (优先遍历传入的 candidates)
        if self._candidates:
            for peer in self._candidates:
                if (
                    peer.name in objective
                    or f"@{peer.name}" in objective
                    or f"@{peer.peer_id}" in objective
                    or peer.peer_id in objective
                ):
                    envelope = self._build_envelope(
                        cid, sender_id, peer.peer_id, objective, context_extra
                    )
                    return TriageDecision(
                        kind=TriageDecisionKind.PEER_HANDOFF,
                        selected_peers=(peer.peer_id,),
                        reasoning=f"显式指定专家队友：{peer.name} ({peer.role})",
                        envelopes=(envelope,),
                    )

        # 2. 未指定 candidates 时，动态查询角色库进行名称匹配
        matched_role = self._match_from_library(objective)
        if matched_role is not None:
            role_id, role_title = matched_role
            envelope = self._build_envelope(cid, sender_id, role_id, objective, context_extra)
            return TriageDecision(
                kind=TriageDecisionKind.PEER_HANDOFF,
                selected_peers=(role_id,),
                reasoning=f"显式指定专家队友：{role_title}",
                envelopes=(envelope,),
            )

        # 3. 复合架构与系统演化任务 -> 自动组队 (TEAM_CAST)
        hit_keywords = [kw for kw in _ARCH_KEYWORDS if kw in lowered]
        if len(hit_keywords) >= 2 or any(kw in lowered for kw in ("重构", "架构", "不变量")):
            team = self._resolve_team_peers()
            envelopes = tuple(
                self._build_envelope(cid, sender_id, peer_id, objective, context_extra)
                for peer_id in team
            )
            return TriageDecision(
                kind=TriageDecisionKind.TEAM_CAST,
                selected_peers=team,
                reasoning=f"识别为复合系统架构议题（命中: {', '.join(hit_keywords)}），激活团队协同",
                envelopes=envelopes,
            )

        # 4. 默认单人收敛 (SOLO)
        return TriageDecision(
            kind=TriageDecisionKind.SOLO,
            selected_peers=(),
            reasoning="常规单步任务，协调者自行处理闭环",
            envelopes=(),
        )

    def _resolve_team_peers(self) -> tuple[str, ...]:
        if self._default_team:
            return self._default_team
        if self._candidates:
            return tuple(c.peer_id for c in self._candidates)
        # 无注入 candidates/default_team 时动态查询角色库，取所有已注册角色 ID
        lib = self._get_role_library()
        if lib is not None:
            try:
                team = tuple(entry.role_id for entry in lib.index() if entry.role_id)
                if team:
                    return team
            except Exception as exc:
                _logger.debug("Error enumerating role library for team fallback: %s", exc)
        _logger.warning(
            "CoordinatorTriageRouter: no candidates, default_team, or role library available; "
            "TEAM_CAST will produce empty peer set."
        )
        return ()

    def _match_from_library(self, objective: str) -> tuple[str, str] | None:
        lib = self._get_role_library()
        if lib is None:
            return None
        try:
            for entry in lib.index():
                title = entry.title
                if not title or len(title) < 2:
                    continue
                # 精确匹配全中文名称或 @ 标识
                if (
                    all("\u4e00" <= ch <= "\u9fff" for ch in title)
                    and title in objective
                ) or f"@{entry.role_id}" in objective:
                    return entry.role_id, title
        except Exception as exc:
            _logger.debug("Error during library role matching: %s", exc)
        return None

    def _get_role_library(self) -> Any | None:
        if self._role_library is not None:
            return self._role_library
        try:
            from lca.agent.role_library import FileRoleLibrary

            self._role_library = FileRoleLibrary()
            return self._role_library
        except Exception:
            return None

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
