"""Typed cross-node state for the think phase graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision

if TYPE_CHECKING:
    from lca.contracts.models.core.state.state import AgentState

CARRY_KEY = "think.subgraph.carry"


@dataclass(slots=True)
class ThinkSubgraphCarry:
    """Working state passed between think subgraph nodes.

    Owned by ``GenericPlanInterpreter._drive``. Step plugins
    must not import or mutate this type.
    """

    state: AgentState
    response: LLMResponse | None = None
    decision: Decision | None = None


__all__ = ["CARRY_KEY", "ThinkSubgraphCarry"]
