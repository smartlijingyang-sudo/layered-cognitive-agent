"""Edge — typed connection between ports.

Borrowed shape from lca/contracts (InfoEdge + InfoEdgeKind).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from agent_lab.primitives.port import PortRef


class EdgeKind(StrEnum):
    DATA = "data"  # pure data flow
    EFFECT = "effect"  # triggers an external side-effect; must emit receipt
    PROJECT = "project"  # enters model-visible closure (mv.assemble input)
    CONTROL = "control"  # gate/approval/routing signal
    BORROW = "borrow"  # cross-spec read via Grant


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    from_ref: PortRef
    to_ref: PortRef
    kind: EdgeKind = EdgeKind.DATA
    required: bool = True
    grant_id: str | None = None

    def label(self) -> str:
        return f"{self.from_ref.label()} --[{self.kind.value}]--> {self.to_ref.label()}"
