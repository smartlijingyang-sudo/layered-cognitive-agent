"""Node + Graph manifests — self-describing building blocks (ADR-0206 §5).

A @node(...) decorator captures everything the framework needs to know
about a node: identity, layer/kind, typed ports, capability declarations,
effect emissions, config schema, and relations to other nodes. Same shape
applies at the graph level (GraphManifest), so graphs compose as
"organizations" of nodes.

Borrowed shape from lca/harness/plugin/declaration.py @plugin(...).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel


class NodeLayer(StrEnum):
    PHASE = "phase"
    MODEL_VISIBLE = "model_visible"
    EFFECT = "effect"
    LINEAGE = "lineage"
    DIGEST = "digest"
    CONTROL = "control"


class NodeKind(StrEnum):
    PASSTHROUGH = "passthrough"  # identity / constant / select
    TRANSFORMER = "transformer"  # redact / dedup / rank / integrate_observation
    ROUTER = "router"  # route_on / join / barrier / discard
    PRODUCER = "producer"  # build_intent / commit_manifest
    VALIDATOR = "validator"  # grant_check / validate_manifest / trust_classify
    EXECUTOR = "executor"  # dispatch_tool / call_llm / write_receipt
    ASSEMBLER = "assembler"  # merge_messages / assemble_messages


class PortKind(StrEnum):
    """Semantic type of port content."""

    ARTIFACT = "artifact"  # generic artifact
    TEXT = "text"  # plain text content
    MESSAGE = "message"  # chat message (openai-style)
    MANIFEST = "manifest"  # frozen ContextManifest
    INTENT = "intent"  # ToolIntent
    RECEIPT = "receipt"  # EffectReceipt
    FACT = "fact"  # structured fact (dict)
    DIGEST = "digest"  # digest pointer
    VERDICT = "verdict"  # grant/approval verdict


@dataclass(frozen=True)
class PortInfo:
    """Self-description of a single port."""

    id: str
    kind: PortKind = PortKind.ARTIFACT
    schema_ref: str = "raw"
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class NodeManifest:
    """Everything the framework needs to know about a node.

    Filled in by @node(...) decorator; available via NodeRegistry.describe(name).
    """

    id: str
    name: str
    layer: NodeLayer
    kind: NodeKind
    description: str = ""
    version: str = "0.1.0"

    inputs: tuple[PortInfo, ...] = ()
    outputs: tuple[PortInfo, ...] = ()

    # Capability declarations (organizational, not data flow)
    provides: tuple[str, ...] = ()  # names of capabilities this node offers
    requires: tuple[str, ...] = ()  # names of capabilities this node needs

    # Effect emissions/consumptions (compile-time check vs edge kinds)
    emits: tuple[str, ...] = ()  # effect class names this node may emit
    consumes: tuple[str, ...] = ()  # effect class names this node may consume

    # Relations to other nodes (organizational graph; not data flow)
    relates_to: tuple[str, ...] = ()  # node ids this node collaborates with

    # Strong-typed config schema (None = free dict)
    config_schema: type[BaseModel] | None = None
    config_schema_ref: str = ""  # dotted import path or YAML ref


@dataclass(frozen=True)
class GraphManifest:
    """Everything the framework needs to know about a graph.

    Populated from YAML `graph:` section or programmatically.
    """

    id: str
    layer: NodeLayer
    purpose: str = ""
    version: str = "0.1.0"

    # Members: node ids declared in this spec
    members: tuple[str, ...] = ()

    # Sub-graphs this spec references (organizational, sub_spec wires data)
    references: tuple[str, ...] = ()

    # Relations to other graphs (organizational)
    relations: tuple[tuple[str, str, str], ...] = ()  # (other_graph_id, kind, role)

    # Capability declarations (graph-level)
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


def _to_layer(v: Any) -> NodeLayer:
    if hasattr(v, "value"):
        return NodeLayer(v.value)
    if isinstance(v, str):
        try:
            return NodeLayer(v)
        except ValueError:
            return NodeLayer.DIGEST
    return NodeLayer.DIGEST


def _to_kind(v: Any) -> NodeKind:
    if hasattr(v, "value"):
        return NodeKind(v.value)
    if isinstance(v, str):
        try:
            return NodeKind(v)
        except ValueError:
            return NodeKind.PASSTHROUGH
    return NodeKind.PASSTHROUGH


def _coerce_ports(items: Any) -> tuple[PortInfo, ...]:
    if items is None:
        return ()
    out: list[PortInfo] = []
    for it in items:
        if isinstance(it, PortInfo):
            out.append(it)
            continue
        # dict or keyword-args
        if isinstance(it, dict):
            kind = it.get("kind", PortKind.ARTIFACT)
            if isinstance(kind, str):
                kind = PortKind(kind) if kind in PortKind._value2member_map_ else PortKind.ARTIFACT
            out.append(
                PortInfo(
                    id=it["id"],
                    kind=kind,
                    schema_ref=it.get("schema_ref", "raw"),
                    required=bool(it.get("required", True)),
                    description=it.get("description", ""),
                )
            )
    return tuple(out)


# Registry of node manifests (filled by @node)
_NODE_MANIFESTS: dict[str, NodeManifest] = {}


class _ManifestStore:
    @staticmethod
    def get(name: str) -> NodeManifest:
        if name not in _NODE_MANIFESTS:
            raise KeyError(f"no manifest registered for node: {name}")
        return _NODE_MANIFESTS[name]

    @staticmethod
    def all() -> dict[str, NodeManifest]:
        return dict(_NODE_MANIFESTS)

    @staticmethod
    def by_layer(layer: NodeLayer) -> list[NodeManifest]:
        return [m for m in _NODE_MANIFESTS.values() if m.layer == layer]

    @staticmethod
    def providing(capability: str) -> list[NodeManifest]:
        return [m for m in _NODE_MANIFESTS.values() if capability in m.provides]


def node(
    *,
    id: str,
    name: str = "",
    layer: NodeLayer | str,
    kind: NodeKind | str,
    description: str = "",
    version: str = "0.1.0",
    inputs: list | None = None,
    outputs: list | None = None,
    provides: list[str] | None = None,
    requires: list[str] | None = None,
    emits: list[str] | None = None,
    consumes: list[str] | None = None,
    relates_to: list[str] | None = None,
    config_schema: type[BaseModel] | None = None,
    config_schema_ref: str = "",
) -> Any:
    """Class decorator — captures a NodeManifest alongside the class.

    Usage:
        @node(id="redact", layer="digest", kind="transformer", inputs=[...], outputs=[...])
        class Redact(Node):
            name = "redact"
            def execute(self, node, inputs): ...
    """
    layer_v = _to_layer(layer)
    kind_v = _to_kind(kind)
    manifest = NodeManifest(
        id=id,
        name=name or id,
        layer=layer_v,
        kind=kind_v,
        description=description,
        version=version,
        inputs=_coerce_ports(inputs),
        outputs=_coerce_ports(outputs),
        provides=tuple(provides or ()),
        requires=tuple(requires or ()),
        emits=tuple(emits or ()),
        consumes=tuple(consumes or ()),
        relates_to=tuple(relates_to or ()),
        config_schema=config_schema,
        config_schema_ref=config_schema_ref,
    )

    def wrap(cls: type) -> type:
        # Stash manifest on the class
        cls._manifest = manifest  # type: ignore[attr-defined]
        # Forward-declared factory name on the class itself
        if not getattr(cls, "name", None) or cls.name == "base":
            cls.name = id
        # Register with the Node registry (mutually agreed with nodes/base.py)
        from agent_lab.nodes.base import register as _register

        _NODE_MANIFESTS[id] = manifest
        return _register(cls)

    return wrap
