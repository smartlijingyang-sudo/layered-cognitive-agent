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
    # ``next_node`` is the control-plane routing target: a node sets it when
    # it wants the kernel/graph scheduler to advance execution to a specific
    # downstream ``semantic_name``. Use it only when the decision actually
    # selects a successor node in the graph.
    next_node: str | None = None
    # ``next_hint`` is free-form metadata forwarded to downstream nodes and
    # the observability surface; it never influences graph routing. Use it
    # to carry rationale, tags, or structured hints (e.g. the reason for
    # short-circuiting) that consumers may read but the scheduler ignores.
    next_hint: str | None = None


__all__ = ["RoutingDecision"]
