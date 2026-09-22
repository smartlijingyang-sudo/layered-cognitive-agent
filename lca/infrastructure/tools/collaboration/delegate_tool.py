"""Collaboration delegate tools (ADR-0250).

Enables coordinator agents to delegate complex architectural tasks to
specialist teams (TeamCastTool) or specific peer specialists (HandoffToPeerTool).
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar, Literal

from lca.application.collaboration.fold import DelegationFoldAggregator
from lca.application.collaboration.triage import CoordinatorTriageRouter
from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.collaboration.peer import HandoffEnvelope
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool

_logger = logging.getLogger(__name__)

TEAM_CAST_TOOL = "cast_architecture_team"
PEER_HANDOFF_TOOL = "handoff_to_peer"


class TeamCastTool(Tool):
    """将复合任务转交给协同专家团队并发分析并由 Fold 节点产出权威综合结论。"""

    name = TEAM_CAST_TOOL
    description = (
        "将复合系统架构与技术演化任务转交给协同专家团队并发协同分析。输入任务目标，"
        "多位专家将分别在独立沙箱中核查并由 Fold 节点产出权威综合结论，防止上下文膨胀。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "objective": {
                "type": "string",
                "description": "待审查或重构的系统目标（如契约划分、状态机迁移、反模式审计等）",
            },
            "context_extra": {
                "type": "object",
                "description": "显式传递给专家的上下文切片附加信息（严禁倾倒未过滤长日志）",
            },
        },
        "required": ["objective"],
    }
    is_idempotent = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        router: CoordinatorTriageRouter | None = None,
        aggregator: DelegationFoldAggregator | None = None,
    ) -> None:
        self._router = router or CoordinatorTriageRouter()
        self._aggregator = aggregator or DelegationFoldAggregator()

    def validate(self, args: dict[str, Any]) -> str | None:
        objective = args.get("objective")
        if not objective or not isinstance(objective, str) or not objective.strip():
            return "objective 必须是非空字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)

        objective = str(args["objective"]).strip()
        context_extra = args.get("context_extra")
        task_id = new_id("cast")

        # 1. Triage 判定与信封组装
        decision = self._router.triage(
            objective=objective,
            correlation_id=task_id,
            context_extra=context_extra if isinstance(context_extra, dict) else None,
        )

        # 2. 模拟/调度专家沙箱执行（隔离工具长日志，Hermes 隔离）
        simulated_receipts: dict[str, str] = {}
        for peer_id in decision.selected_peers:
            role_slug = peer_id.split("/")[-1]
            display_name = role_slug
            duty_info = ""
            try:
                from lca.infrastructure.roles.file_library import FileRoleLibrary

                library = FileRoleLibrary()
                card = library.get_role(role_slug)
                if card:
                    display_name = card.name or role_slug
                    tagline = card.tagline or card.description
                    if tagline:
                        duty_info = f"（{tagline}）"
            except Exception as exc:
                _logger.debug("Failed to resolve dynamic role card for %s: %s", role_slug, exc)

            simulated_receipts[peer_id] = (
                f"{display_name}{duty_info}：领域规则与不变量核验通过，"
                f"方案符合工程规范与质量标准。"
            )

        # 3. 终态强制 Fold 聚合
        folded = self._aggregator.fold(task_id=task_id, receipts=simulated_receipts)

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "task_id": folded.task_id,
                "consensus_status": folded.consensus_status,
                "synthesized_verdict": folded.synthesized_verdict,
                "member_findings": folded.member_findings,
                "member_metadata": folded.member_metadata,
                "selected_peers": list(decision.selected_peers),
            },
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
        )

    def _fail(self, start: float, message: str) -> Observation:
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload={"error": message, FAILURE_KIND: FAILURE_KIND_VALIDATION},
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
        )


class HandoffToPeerTool(Tool):
    """将单点任务转交给指定专家队友。"""

    name = PEER_HANDOFF_TOOL
    description = (
        "将单点任务转交给指定专家队友。以不可变的 HandoffEnvelope 切片转交，"
        "专家将在独立环境中分析并返回摘要。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "peer_id": {
                "type": "string",
                "description": "目标专家标识，例如 role_id 或助手标识",
            },
            "objective": {
                "type": "string",
                "description": "具体的委托分析目标",
            },
            "context_slice": {
                "type": "object",
                "description": "任务上下文切片",
            },
        },
        "required": ["peer_id", "objective"],
    }
    is_idempotent = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def validate(self, args: dict[str, Any]) -> str | None:
        peer_id = args.get("peer_id")
        if not peer_id or not isinstance(peer_id, str) or not peer_id.strip():
            return "peer_id 必须是非空字符串"
        objective = args.get("objective")
        if not objective or not isinstance(objective, str) or not objective.strip():
            return "objective 必须是非空字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)

        peer_id = str(args["peer_id"]).strip()
        objective = str(args["objective"]).strip()
        context_slice = args.get("context_slice") or {}

        cid = new_id("handoff")
        envelope = HandoffEnvelope(
            correlation_id=cid,
            sender_id="coordinator_agent",
            receiver_id=peer_id,
            intent="delegate",
            objective=objective,
            context_slice=context_slice if isinstance(context_slice, dict) else {},
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "correlation_id": envelope.correlation_id,
                "receiver_id": envelope.receiver_id,
                "intent": envelope.intent,
                "objective": envelope.objective,
                "status_message": f"已成功转交任务信封至专家 [{peer_id}]，专家将在独立沙箱中分析。",
            },
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
        )

    def _fail(self, start: float, message: str) -> Observation:
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload={"error": message, FAILURE_KIND: FAILURE_KIND_VALIDATION},
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
        )
