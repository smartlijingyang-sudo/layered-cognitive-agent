from __future__ import annotations

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.terminal_outcome import ResumeCursor
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeRunOutcome,
    DeclarativeValidationError,
)
from lca.contracts.protocols.journal.artifact_closure import ArtifactClosure
from lca.contracts.protocols.runtime.infra import StateStore
from lca.contracts.protocols.runtime.runtime_composition import ResultFinalizer
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.declarative.execute.interpreter import InterpretationResult
from lca.runtime.result_projection import TerminalResultProjection


class RuntimeResultFinalizer(ResultFinalizer):
    """Close an interpreted run through hooks, reducer folding, and projection.

    Runtime work stays here: invoke completion hooks, add artifact closure, and
    ask the sole State writer to fold a terminal fact.  Carrier ``Result``
    fields, persistence references, and approval resume metadata belong to
    ``TerminalResultProjection`` so fresh and resumed paths share one read-side
    interface.
    """

    def __init__(
        self,
        *,
        reducer: Reducer,
        hooks: HookRegistry,
        artifact_closure: ArtifactClosure | None = None,
        state_store: StateStore | None,
    ) -> None:
        self._reducer = reducer
        self._hooks = hooks
        # ADR-0158 决策 二:artifact_closure 不再被 reducer 流消费;
        # closure 改走 transport projection 通道。参数保留(deprecated)以兼容
        # 既有 caller;后续 commit 删字段时同步删 caller 端 artifact_closure。
        self._artifact_closure = artifact_closure
        self._result_projection = TerminalResultProjection(state_store)

    async def finalize(
        self,
        *,
        interpretation: InterpretationResult,
        plan_ref: str,
        journal_sequence: int,
    ) -> Result:
        """Close one execution path and project its carrier-safe result.

        ADR-0158 决策 二:closure 不再经 reducer 流,改走 transport projection
        通道。reducer 仍是 state 唯一 writer(ADR-0070 C4)。
        """
        final_state = interpretation.state
        await self._hooks.trigger("on_complete", final_state)

        outcome = interpretation.outcome
        if outcome is None:
            raise DeclarativeValidationError(
                "RT-004",
                "terminal interpreter result must carry a DeclarativeRunOutcome",
            )
        if outcome.kind == "failed":
            final_state = self._reducer.apply_error(
                final_state,
                RuntimeError(_runtime_failure_message(outcome)),
            )
        if outcome.kind == "paused":
            final_state = self._reducer.apply_paused(final_state, outcome.cursor)

        terminal_outcome = self._reducer.apply_terminal_outcome(
            final_state,
            outcome.stop,
            plan_ref=plan_ref,
            journal_seq_end=journal_sequence,
            resume_cursor=_resume_cursor(outcome, journal_sequence=journal_sequence),
        )
        return await self._result_projection.project(
            final_state,
            terminal_outcome=terminal_outcome,
            declarative_outcome=outcome,
        )


def _resume_cursor(
    outcome: DeclarativeRunOutcome,
    *,
    journal_sequence: int,
) -> ResumeCursor | None:
    """Translate a declared pause into the terminal outcome's durable cursor."""
    if outcome.kind != "paused":
        return None
    if not isinstance(journal_sequence, int) or isinstance(journal_sequence, bool):
        raise ValueError("journal_sequence must be an integer")
    if journal_sequence < 0:
        raise ValueError("journal_sequence must be non-negative")
    request = outcome.approval_request
    if not isinstance(request, dict):
        raise ValueError("paused declarative run requires an approval request")
    approval_id = request.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        raise ValueError("paused declarative run requires a non-empty approval_id")
    return ResumeCursor(
        cursor=outcome.cursor.node_id,
        session_seq=journal_sequence,
        approval_id=approval_id,
    )


def _runtime_failure_message(outcome: DeclarativeRunOutcome) -> str:
    """Build the reducer error text before its terminal fact is folded."""
    if outcome.error_fact is not None and isinstance(outcome.error_fact.payload, dict):
        payload = outcome.error_fact.payload
        detail = payload.get("detail") or payload.get("error")
        if detail:
            return str(detail)
    return "declarative run failed"


__all__ = ["RuntimeResultFinalizer"]
