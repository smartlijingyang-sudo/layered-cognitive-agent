"""InfoEdgeSpec — the *single* executable graph kind (ADR-0206 C11).

Borrowed vocabulary from ADR-0206 §1 + §5; pure declarative data.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.primitives.edge import Edge


class NodeRegion(StrEnum):
    PHASE = "phase"  # region = phase:<name>
    MODEL_VISIBLE = "model_visible"
    EFFECT = "effect"
    LINEAGE = "lineage"
    DIGEST = "digest"
    CONTROL = "control"


class ErrorRoute(StrEnum):
    FAIL = "fail"
    RETRY = "retry"
    ROUTE = "route"


class InfoNode(BaseModel):
    """Single-purpose worker declaration: inputs, outputs, which factory to call."""

    model_config = ConfigDict(extra="forbid")

    id: str
    region: NodeRegion = NodeRegion.DIGEST
    factory: str = "identity"  # name -> registry lookup at runtime
    config: dict[str, Any] = Field(default_factory=dict)
    ins: list[str] = Field(default_factory=list)
    outs: list[str] = Field(default_factory=list)
    on_error: ErrorRoute = ErrorRoute.FAIL
    route_to: str | None = None
    parallelism: int = 1


class SubSpecLink(BaseModel):
    """Reference to a nested InfoEdgeSpec by a node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    sub_spec_id: str
    # schema-ref strings used to check parent port <-> sub_spec export compatibility
    input_map: dict[str, str] = Field(default_factory=dict)  # parent_port -> sub_spec_export
    output_map: dict[str, str] = Field(default_factory=dict)  # sub_spec_export -> parent_port


class BindSpec(BaseModel):
    """YAML-shaped Bind selector for a PluginRef.

    Mirrors ``agent_lab.plugins.base.Bind`` so the yaml schema is
    framework-agnostic (no plugin import required to load).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str  # "event_kind" only
    value: str


class PluginRef(BaseModel):
    """YAML-shaped reference to a GraphPlugin.

    Plugins extend graphs with cross-cutting behavior (event emission,
    metrics, control binding, parse rules, etc.). The graph spec carries
    a list of PluginRef; the compiler + runner resolve them through
    ``agent_lab.plugins.resolve_plugin``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str
    binds: tuple[BindSpec, ...] = Field(default_factory=tuple)
    config: dict[str, Any] = Field(default_factory=dict)


class InfoGrant(BaseModel):
    """Cross-spec read license (ADR-0206 C4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    from_spec: str
    to_spec: str
    ports: list[str] = Field(default_factory=list)
    mode: str = "read"  # read | consume
    max_bytes: int = 0  # 0 = unlimited
    redact: list[str] = Field(default_factory=list)


class InfoEdgeSpec(BaseModel):
    """The only executable graph kind. Region-tagged for semantics."""

    model_config = ConfigDict(extra="forbid")

    id: str
    version: str = "0.1.0"
    region: NodeRegion = NodeRegion.DIGEST
    description: str = ""
    # Opaque phase tag (from yaml ``phase:`` / ``region: phase:<name>``).
    # Skeleton does not interpret it; business plugins (e.g. control_slots)
    # may use it as a lookup key. Empty when unset.
    phase: str = ""

    nodes: list[InfoNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    grants: list[InfoGrant] = Field(default_factory=list)
    sub_specs: list[SubSpecLink] = Field(default_factory=list)
    plugins: list[PluginRef] = Field(default_factory=list)

    # Optional terminal: node whose OUT triggers "discard" if effect receipt has nowhere to land
    discard_sink: str | None = None

    def node(self, node_id: str) -> InfoNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"node not found: {node_id} in spec {self.id}")

    def initial_ports(self) -> set[str]:
        """Return port_ids that are wired from the synthetic `_initial` source node.

        These are the external inputs a caller must supply when running this spec.
        """
        ports: set[str] = set()
        for e in self.edges:
            if e.from_ref.node_id == "_initial":
                ports.add(e.from_ref.port_id)
        return ports
