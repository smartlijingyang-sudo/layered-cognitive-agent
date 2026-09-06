"""Prepared act-phase journal facts (ADR-0194 P1-11).

Cognition body prepares :class:`ActJournalReceipt`; loop layer commits via
``act_journal_commit`` (legacy ``JournalEvent`` until Session catalog migration).
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import (
    ApprovalRequested,
    DecisionMade,
    JournalEvent,
    SynthesisCompleted,
    TeamMessagePublished,
)
from lca.contracts.models.team.consultation import SynthesisMethod
from lca.contracts.protocols.runtime.infra import Tool


@dataclass(frozen=True, slots=True)
class ActJournalReceipt:
    """One prepared legacy act journal fact ready for loop commit."""

    journal_event: JournalEvent
    actor: str = "body"


def decision_made_receipt(decision: Decision, state: AgentState) -> ActJournalReceipt:
    """Build a ``DecisionMade`` journal receipt from an authorized decision."""
    delegate_target = ""
    delegate_count = 0
    if decision.delegations:
        first = decision.delegations[0]
        delegate_target = first.target_role or first.target_agent_id or ""
        delegate_count = len(decision.delegations) if len(decision.delegations) > 1 else 0
    tool_name = decision.tool_calls[0].tool_name if decision.tool_calls else ""
    return ActJournalReceipt(
        journal_event=DecisionMade(
            step=state.step,
            action_type=decision.action_type,
            rationale_preview=decision.rationale,
            delegate_target=delegate_target,
            delegate_count=delegate_count,
            tool_name=tool_name,
            confidence=decision.confidence,
            response_text=decision.response_text or "",
        ),
    )


def synthesis_completed_receipt(
    *,
    method: SynthesisMethod | str,
    candidate_count: int,
    output_text: str,
) -> ActJournalReceipt:
    """Build a ``SynthesisCompleted`` journal receipt for board synthesis."""
    method_value = method.value if isinstance(method, SynthesisMethod) else str(method)
    return ActJournalReceipt(
        journal_event=SynthesisCompleted(
            method=method_value,
            candidate_count=candidate_count,
            output_text=output_text,
        ),
    )


def approval_requested_receipt(
    tool: Tool,
    invocation_id: str,
    *,
    risk_level: str = "human-input",
) -> ActJournalReceipt:
    """Build an ``ApprovalRequested`` journal receipt for HIL tool pause."""
    return ActJournalReceipt(
        journal_event=ApprovalRequested(
            envelope_id=invocation_id,
            tool_name=tool.name,
            capability_grant=tool.name,
            risk_level=risk_level,
        ),
    )


def team_message_published_receipt(
    *,
    team_id: str,
    thread_id: str,
    sender_role: str,
    recipient_role: str,
    body_preview: str,
    step: int = 0,
) -> ActJournalReceipt:
    """Build a ``TeamMessagePublished`` journal receipt for team inbox fold."""
    return ActJournalReceipt(
        journal_event=TeamMessagePublished(
            team_id=team_id,
            thread_id=thread_id,
            sender_role=sender_role,
            recipient_role=recipient_role,
            step=step,
            body_preview=body_preview,
        ),
    )


__all__ = [
    "ActJournalReceipt",
    "approval_requested_receipt",
    "decision_made_receipt",
    "synthesis_completed_receipt",
    "team_message_published_receipt",
]
