"""Build DeliveryEvidence from AgentState manifest and control turns (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.material import artifact_count
from lca.cognition.convergence.payload import (
    turn_has_delivery_signal,
)
from lca.cognition.convergence.predicates import delivery_satisfied
from lca.cognition.convergence.producer_tools import is_producer_tool
from lca.cognition.convergence.task_class import resolve_task_class
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.policy.convergence import DeliveryEvidence
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.context.turn_control_reader import control_turns


def _is_use_tool(action_type: object) -> bool:
    return action_type == ActionType.USE_TOOL or action_type == "use_tool"


def _producer_success_count(state: AgentState) -> int:
    count = 0
    for turn in control_turns(state):
        if not _is_use_tool(turn.action_type):
            continue
        if not is_producer_tool(turn.tool_name):
            continue
        if turn.observation_success:
            count += 1
    return count


def _has_user_visible_delivery(state: AgentState) -> bool:
    for turn in control_turns(state):
        if not _is_use_tool(turn.action_type):
            continue
        if not is_producer_tool(turn.tool_name):
            continue
        if not turn.observation_success:
            continue
        if turn_has_delivery_signal(
            turn.observation_payload,
            files_created=turn.files_created,
        ):
            return True
    return False


def build_delivery_evidence(state: AgentState) -> DeliveryEvidence:
    task_class = resolve_task_class(state)
    artifacts = artifact_count(state)
    producer_ok = _producer_success_count(state)
    user_visible = _has_user_visible_delivery(state)
    satisfied, detail = delivery_satisfied(
        task_class,
        artifact_count=artifacts,
        producer_ok=producer_ok,
        has_user_visible_delivery=user_visible,
    )
    return DeliveryEvidence(
        task_class=task_class,
        artifact_count=artifacts,
        has_user_visible_text=user_visible,
        producer_success_since_task=producer_ok,
        satisfied=satisfied,
        detail=detail,
    )


__all__ = ["build_delivery_evidence"]
