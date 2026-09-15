"""RoutingDecision — typed control-plane output of decision-producing nodes.

Replaces the three ad-hoc fields ``NodeOutput.result_kind``,
``NodeOutput.next_hint``, ``NodeOutput.next_hints``. The kernel reads the same
port store — no separate control channel.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums.enums import ActionType


class RoutingDecision(BaseModel):
    """Typed control-plane output every decision-producing node emits."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    action_type: ActionType
    should_terminate: bool = False
    next_node: str | None = None  # target node semantic_name for graph routing
    next_hint: str | None = None  # free-form metadata, not routing


__all__ = ["RoutingDecision"]
