"""Typed, structured predicates over port names.

Replaces the string DSL (``when: result.payload.decision.action_type == "use_tool"``).
Every cross-node read is a typed :class:`PortRef`, validated at plan lift.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.ports import PortName


class PortRef(BaseModel):
    """Symbolic reference to a port on the source node of an edge.

    Resolved by the kernel against the source node's declared outputs.
    Fails at lift time if the source node does not declare this port.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: PortName
    field: str | None = None  # typed against port.payload_type at lift


class Predicate(BaseModel):
    """Typed, structured predicate over port names.

    Leaf kinds compare a port value to a constant; inner kinds combine
    via and/or/not. No attribute paths, no string parsing, no AST.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["eq", "ne", "in", "exists", "missing", "and", "or", "not"]
    port: PortRef | None = None
    value: Any | None = None
    children: tuple[Predicate, ...] = ()


__all__ = ["PortRef", "Predicate"]
