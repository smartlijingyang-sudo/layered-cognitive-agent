"""Project durable declarative terminal facts into carrier ``Result`` values.

``RuntimeResultFinalizer`` owns runtime hooks and reducer folding.  This module
owns the remaining read-side work: persist the final state once, expose terminal
metadata, and preserve the resume data required by a paused run.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.ids import TraceId, new_id
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState, Budget, StateSnapshot
from lca.contracts.models.core.terminal_outcome import (
    ArtifactRef,
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeRunOutcome,
    DeclarativeValidationError,
)
from lca.contracts.protocols.runtime.infra import StateStore


class TerminalResultProjection:
    """Convert terminal facts and declarative outcomes into the carrier result.

    This is deliberately the sole public projection interface for fresh and
    resumed runs.  It keeps the persistence reference, approval payload, phase
    cursor, and result status derived from the same immutable terminal facts.
    """

    def __init__(self, state_store: StateStore | None) -> None:
        self._state_store = state_store

    async def project(
        self,
        final_state: AgentState,
        *,
        terminal_outcome: TerminalOutcome,
        declarative_outcome: DeclarativeRunOutcome | None,
    ) -> Result:
        """Project one finalized execution from the sole terminal fact."""
        return await self._project_terminal_outcome(
            final_state,
            terminal_outcome,
            declarative_outcome,
        )

    async def _project_terminal_outcome(
        self,
        final_state: AgentState,
        terminal_outcome: TerminalOutcome,
        declarative_outcome: DeclarativeRunOutcome | None,
    ) -> Result:
        saved_ref = await self._save_state(final_state)
        extra = self._terminal_extra(
            final_state,
            terminal_outcome,
            declarative_outcome,
            saved_ref=saved_ref,
        )
        budget_used = getattr(final_state, "budget", None) or Budget()
        return Result(
            trace_id=getattr(final_state, "trace_id", "") or "",
            status=_status_for_terminal_kind(terminal_outcome.kind),
            final_state_ref=saved_ref
            or f"mem://{getattr(final_state, 'trace_id', '')}/{getattr(final_state, 'step', 0)}",
            total_steps=getattr(final_state, "step", 0) + 1,
            budget_used=budget_used,
            output=_terminal_output(terminal_outcome),
            error=(
                terminal_outcome.error_ref.message
                if terminal_outcome.error_ref is not None
                else None
            ),
            extra=extra,
        )

    async def _save_state(self, final_state: AgentState) -> str | None:
        if self._state_store is None:
            return None
        saved_ref = await self._state_store.save(final_state)
        if not saved_ref:
            raise DeclarativeValidationError("PG-008", "StateStore returned an empty state_ref")
        return str(saved_ref)

    def _terminal_extra(
        self,
        final_state: AgentState,
        terminal_outcome: TerminalOutcome,
        declarative_outcome: DeclarativeRunOutcome | None,
        *,
        saved_ref: str | None,
    ) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if saved_ref is not None:
            extra["state_ref"] = saved_ref
        if terminal_outcome.kind is TerminalOutcomeKind.WAITING_INPUT:
            if saved_ref is None:
                raise DeclarativeValidationError(
                    "PG-008",
                    "waiting input requires a durable StateStore",
                )
            if terminal_outcome.resume_cursor is not None:
                extra["resume_cursor"] = {
                    "cursor": terminal_outcome.resume_cursor.cursor,
                    "session_seq": terminal_outcome.resume_cursor.session_seq,
                    "approval_id": terminal_outcome.resume_cursor.approval_id,
                }
            if declarative_outcome is not None:
                self._add_approval_details(extra, declarative_outcome)
            if declarative_outcome is not None and declarative_outcome.cursor is not None:
                extra["phase_cursor"] = declarative_outcome.cursor
                if saved_ref is not None:
                    extra["state_snapshot"] = StateSnapshot(
                        snapshot_id=new_id("snap"),
                        step=final_state.step,
                        state_ref=saved_ref,
                        phase_cursor=declarative_outcome.cursor,
                        trace_id=TraceId(final_state.trace_id),
                    )
        if terminal_outcome.artifact_refs:
            extra["artifact_refs"] = [
                {
                    "artifact_id": reference.artifact_id,
                    "plan_ref": reference.plan_ref,
                    "artifact_kind": reference.artifact_kind,
                }
                for reference in terminal_outcome.artifact_refs
                if isinstance(reference, ArtifactRef)
            ]
        extra["plan_ref"] = terminal_outcome.plan_ref
        extra["journal_seq_end"] = terminal_outcome.journal_seq_end
        extra["terminal_outcome_kind"] = terminal_outcome.kind.value
        return extra

    @staticmethod
    def _add_approval_details(
        extra: dict[str, Any],
        outcome: DeclarativeRunOutcome,
    ) -> None:
        approval = (
            outcome.approval_request
            if isinstance(outcome.approval_request, dict)
            else {"type": "approval_pending"}
        )
        extra["approval_request"] = approval
        extra["phase_cursor"] = outcome.cursor


def _status_for_terminal_kind(kind: TerminalOutcomeKind) -> TaskStatus:
    statuses = {
        TerminalOutcomeKind.COMPLETED: TaskStatus.COMPLETED,
        TerminalOutcomeKind.FAILED: TaskStatus.FAILED,
        TerminalOutcomeKind.CANCELED: TaskStatus.CANCELED,
        TerminalOutcomeKind.WAITING_INPUT: TaskStatus.INPUT_REQUIRED,
        TerminalOutcomeKind.DEGRADED: TaskStatus.FAILED,
    }
    return statuses.get(kind, TaskStatus.FAILED)


def _terminal_output(terminal_outcome: TerminalOutcome) -> str | None:
    reference = terminal_outcome.final_output_ref
    if isinstance(reference, TextRef):
        return str(reference.text)
    return str(reference) if reference else None


__all__ = ["TerminalResultProjection"]
