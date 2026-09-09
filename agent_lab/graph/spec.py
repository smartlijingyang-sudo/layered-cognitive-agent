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


# ---------------------------------------------------------------------------
# ADR-0210 §6.3 — runtime region label construction + nested subgraph walk
# ---------------------------------------------------------------------------

def current_region_label(spec: "InfoEdgeSpec") -> str:
    """Build the full region label for an InfoEdgeSpec instance.

    Composes ``spec.region.value`` + ``spec.phase`` into the label the
    C14 region check uses (per ADR-0210 §3 P7-I-1). Used at runtime to
    stamp the spec's region into spine events and lineage so a recorder
    can see *which* phase a node ran under (per ADR-0206 §13 C13).

    Returns one of:
      - ``phase:<phase>`` (when region == PHASE and phase is non-empty)
      - ``region.value`` (bare-enum: model_visible / effect / etc.)
      - ``region:phase:<unnamed>`` (PHASE with empty phase — flagged by
        the validator as a P7-I-4 violation)
    """
    enum_value = spec.region.value if hasattr(spec.region, "value") else str(spec.region)
    phase_name = (getattr(spec, "phase", "") or "").strip()
    if enum_value == "phase":
        return f"phase:{phase_name}" if phase_name else "phase:<unnamed>"
    return enum_value


def walk_sub_specs(root: "InfoEdgeSpec") -> "list[InfoEdgeSpec]":
    """Return the depth-first traversal of the sub_spec graph under root.

    The root is included as the first element. Sub_specs are looked up by
    their ``sub_spec_id`` in the caller-supplied ``registry``; if a
    sub_spec id is not in the registry it is skipped (the caller should
    have validated references during the C6 port check).

    The walker is iterative (not recursive on the Python call stack) to
    avoid RecursionError on deeply-nested sub_spec chains.
    """
    return _walk_sub_specs(root, registry=None, _seen=None)


def _walk_sub_specs(
    spec: "InfoEdgeSpec",
    registry: "dict[str, InfoEdgeSpec] | None",
    _seen: "set[str] | None",
) -> "list[InfoEdgeSpec]":
    if _seen is None:
        _seen = set()
    out: list[InfoEdgeSpec] = []
    if spec.id in _seen:
        return out
    _seen.add(spec.id)
    out.append(spec)
    for link in spec.sub_specs:
        sub = (registry or {}).get(link.sub_spec_id)
        if sub is None:
            continue  # unresolvable — caller-side C6 will have caught it
        out.extend(_walk_sub_specs(sub, registry, _seen))
    return out


__all__ = [
    "NodeRegion",
    "ErrorRoute",
    "InfoNode",
    "SubSpecLink",
    "BindSpec",
    "PluginRef",
    "InfoGrant",
    "InfoEdgeSpec",
    "current_region_label",
    "walk_sub_specs",
]
