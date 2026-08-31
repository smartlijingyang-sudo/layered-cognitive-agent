"""Resolve a declarative checkpoint into the state required for one resumed Turn.

This module owns the recovery seam between a durable checkpoint and the generic
phase-graph interpreter.  Callers supply the plan identity from their already
bound execution context; this module validates that identity, selects the
explicit post-resume state or durable state source, and preserves the legacy
cursor attribute only where an older state implementation exposes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.state import AgentState, StateSnapshot
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseRunCursor,
)
from lca.contracts.protocols.runtime.infra import StateStore
from lca.contracts.protocols.runtime.runtime_composition import CheckpointStateResolver


@dataclass(frozen=True, slots=True)
class DeclarativeCheckpoint:
    """All durable references and in-process state needed to resume one Turn.

    ``resume_state`` is optional because a caller that has already applied a
    resume command can avoid a redundant StateStore round-trip.  Without it,
    ``state_snapshot.state_ref`` is the durable source of truth.
    """

    state_snapshot: StateSnapshot
    cursor: PhaseRunCursor
    plan_ref: str
    resume_state: AgentState | None = None

    def __post_init__(self) -> None:
        if not self.plan_ref:
            raise ValueError("checkpoint plan_ref must not be empty")
        if self.cursor.plan_ref != self.plan_ref:
            raise ValueError("checkpoint cursor and plan_ref must match")
        snapshot_cursor = self.state_snapshot.phase_cursor
        if snapshot_cursor is not None and snapshot_cursor.plan_ref != self.plan_ref:
            raise ValueError("checkpoint snapshot and plan_ref must match")


class DeclarativeCheckpointStateResolver(CheckpointStateResolver):
    """Turn a verified declarative checkpoint into the state for interpretation.

    The public interface deliberately exposes one operation: a checkpoint plus
    the plan identity accepted by the enclosing execution context becomes an
    ``AgentState`` ready for ``GenericPlanInterpreter.resume``.  It hides the
    recovery source priority, fail-closed diagnostics, and legacy cursor
    compatibility from carrier adapters.
    """

    def __init__(self, *, state_store: StateStore | None) -> None:
        self._state_store = state_store

    async def resolve(
        self,
        checkpoint: DeclarativeCheckpoint,
        *,
        expected_plan_ref: str,
    ) -> AgentState:
        """Validate and materialize the state for a resumed declarative Turn."""

        self._require_matching_plan_ref(checkpoint, expected_plan_ref)
        state = await self._load_state(checkpoint)
        self._restore_legacy_cursor(state, checkpoint.cursor)
        return state

    @staticmethod
    def _require_matching_plan_ref(
        checkpoint: DeclarativeCheckpoint,
        expected_plan_ref: str,
    ) -> None:
        if checkpoint.plan_ref != expected_plan_ref:
            raise DeclarativeValidationError(
                "PG-008",
                "plan_ref mismatch: "
                f"checkpoint.plan_ref ({checkpoint.plan_ref!r}) != "
                f"expected plan_ref ({expected_plan_ref!r})",
            )

    async def _load_state(self, checkpoint: DeclarativeCheckpoint) -> AgentState:
        if checkpoint.resume_state is not None:
            return checkpoint.resume_state
        if self._state_store is None:
            raise DeclarativeValidationError(
                "PG-008",
                "Declarative resume requires a StateStore when checkpoint.resume_state is absent.",
            )
        return await self._state_store.load(checkpoint.state_snapshot.state_ref)

    @staticmethod
    def _restore_legacy_cursor(state: AgentState, cursor: PhaseRunCursor) -> None:
        """Preserve the old dynamic cursor only for state objects that expose it.

        New checkpoints keep the cursor on ``StateSnapshot``.  Older runtime
        states may still expose a ``phase_cursor`` attribute, so retaining this
        narrow compatibility step prevents a refactor of checkpoint resolution
        from changing their behavior while keeping the compatibility detail
        local to the recovery seam.
        """

        if getattr(state, "phase_cursor", None) is not None:
            object.__setattr__(state, "phase_cursor", cursor)


# ── ADR-0110 D5 / PR-E:「Declarative」前缀公开 re-export ────────────
RuntimeCheckpoint = DeclarativeCheckpoint
"""Public alias for ``DeclarativeCheckpoint`` (ADR-0110 D5)."""


__all__ = [
    "DeclarativeCheckpoint",
    "DeclarativeCheckpointStateResolver",
    "RuntimeCheckpoint",
]
