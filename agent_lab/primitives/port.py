"""Port — typed input/output handle.

Borrowed shape from lca/contracts/ (PortRef + schema-ref). Pure data.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PortDir(StrEnum):
    IN = "in"
    OUT = "out"


class PortTag(StrEnum):
    FACT = "fact"
    PROJECTION = "projection"
    EFFECT = "effect"
    CONTROL = "control"


class Port(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    dir: PortDir
    type: str = "Any"  # schema ref string
    tag: PortTag = PortTag.FACT
    optional: bool = False


class PortRef(BaseModel):
    """Where a port lives: inside an InfoNode, optionally in a nested InfoEdgeSpec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str
    node_id: str
    port_id: str

    def label(self) -> str:
        return f"{self.spec_id}/{self.node_id}.{self.port_id}"
