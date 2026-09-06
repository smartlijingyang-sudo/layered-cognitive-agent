"""RunCommitter — Reducer evolution seam (ADR-0191 Wave C).

RunCommitter is the control-plane commit boundary. Default implementations
delegate to :class:`lca.contracts.protocols.state.reducer.Reducer`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.state.reducer import Reducer


@runtime_checkable
class RunCommitter(Reducer, Protocol):
    """Control-plane state commit; extends Reducer without new model-wire duties."""

    def commit_turn(
        self,
        state: AgentState,
        turn: Turn,
        *,
        session: object | None = None,
    ) -> AgentState:
        """Fold a completed turn into control state; optional Session fact append."""
        ...


__all__ = ["RunCommitter"]
