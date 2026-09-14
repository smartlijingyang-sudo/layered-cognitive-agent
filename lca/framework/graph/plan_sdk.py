"""Plan SDK — typed Python surface for constructing plan graphs.

Provides convenience builders over the contract-layer Pydantic types
(:class:`Plan`, :class:`PlanNode`, :class:`PlanEdge`, :class:`Predicate`,
:class:`PortRef`, :class:`RoutingDecision`). Every builder returns a
typed Pydantic model; no raw dicts leak through the public API.

Serialization produces YAML matching the v2 BundleGraphSpec shape
(structured ``when`` predicates, not string DSL). Parsing reverses
the process so ``parse_plan_yaml(serialize_plan(p))`` recovers the
same ``Plan`` with typed :class:`Predicate` objects on every edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.routing import RoutingDecision

# ---------------------------------------------------------------------------
# Port construction
# ---------------------------------------------------------------------------


def port(
    name: PortName,
    *,
    payload_type: type | None = None,
    required: bool = True,
) -> PortRef:
    """Create a typed :class:`PortRef` for use inside predicates.

    ``payload_type`` is accepted for forward compatibility (future
    lift-time field validation) but not stored on the PortRef — the
    Predicate contract does not carry per-reference type metadata.
    """
    return PortRef(name=name)


# ---------------------------------------------------------------------------
# Predicate factories
# ---------------------------------------------------------------------------


def eq(p: PortRef, value: Any) -> Predicate:
    """``port == value``."""
    return Predicate(kind="eq", port=p, value=value)


def ne(p: PortRef, value: Any) -> Predicate:
    """``port != value``."""
    return Predicate(kind="ne", port=p, value=value)


def in_(p: PortRef, values: Sequence[Any]) -> Predicate:
    """``port in values``."""
    return Predicate(kind="in", port=p, value=list(values))


def exists(p: PortRef) -> Predicate:
    """``port is not None``."""
    return Predicate(kind="exists", port=p)


def missing(p: PortRef) -> Predicate:
    """``port is None``."""
    return Predicate(kind="missing", port=p)


def and_(*preds: Predicate) -> Predicate:
    """Boolean AND over child predicates."""
    return Predicate(kind="and", children=tuple(preds))


def or_(*preds: Predicate) -> Predicate:
    """Boolean OR over child predicates."""
    return Predicate(kind="or", children=tuple(preds))


def not_(pred: Predicate) -> Predicate:
    """Boolean NOT of a single child predicate."""
    return Predicate(kind="not", children=(pred,))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def routing(
    action_type: ActionType | str,
    *,
    should_terminate: bool = False,
    next_hint: str | None = None,
) -> RoutingDecision:
    """Build a typed :class:`RoutingDecision`."""
    return RoutingDecision(
        action_type=ActionType(action_type),
        should_terminate=should_terminate,
        next_hint=next_hint,
    )


# ---------------------------------------------------------------------------
# Node / Edge / Plan constructors
# ---------------------------------------------------------------------------


def node(
    id: str,
    binding: BindingKind | str,
    *,
    inputs: Sequence[PortSpec] = (),
    outputs: Sequence[PortSpec] = (),
    terminal_predicate: Predicate | None = None,
    max_visits: int = 1,
    terminal: bool = False,
    entry: bool = False,
    subgraph_ref: SubgraphReference | None = None,
    **config: Any,
) -> PlanNode:
    """Build a :class:`PlanNode` with typed IO schema and config extras."""
    if isinstance(binding, str):
        binding = BindingKind(binding)
    return PlanNode(
        id=id,
        binding=binding,
        io_schema=NodeIOSchema(
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            terminal_predicate=terminal_predicate,
        ),
        config=config,
        max_visits=max_visits,
        terminal=terminal,
        entry=entry,
        subgraph_ref=subgraph_ref,
    )


def edge(
    source: str,
    target: str,
    *,
    when: Predicate | None = None,
    subgraph_ref: SubgraphReference | None = None,
) -> PlanEdge:
    """Build a :class:`PlanEdge`. ``when=None`` defaults to ``"true"``."""
    kwargs: dict[str, Any] = {"source": source, "target": target}
    if when is not None:
        kwargs["when"] = when
    if subgraph_ref is not None:
        kwargs["subgraph_ref"] = subgraph_ref
    return PlanEdge(**kwargs)


def plan(
    id: str,
    *,
    nodes: Sequence[PlanNode],
    edges: Sequence[PlanEdge] = (),
    approval_resume_node: str | None = None,
) -> Plan:
    """Build a :class:`Plan`."""
    return Plan(
        id=id,
        nodes=tuple(nodes),
        edges=tuple(edges),
        approval_resume_node=approval_resume_node,
    )


# ---------------------------------------------------------------------------
# Serialization: Plan → YAML (v2 BundleGraphSpec shape)
# ---------------------------------------------------------------------------

# Keys already emitted at the node top level; must not duplicate from config.
_PLAN_NODE_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "binding",
        "io_schema",
        "config",
        "max_visits",
        "terminal",
        "entry",
        "subgraph_ref",
        "inner_io_schema",
    }
)


def _predicate_to_dict(pred: Predicate) -> dict[str, Any]:
    """Serialize a Predicate to a YAML-compatible dict."""
    if pred.kind in ("and", "or"):
        return {
            "kind": pred.kind,
            "children": [_predicate_to_dict(c) for c in pred.children],
        }
    if pred.kind == "not":
        return {
            "kind": "not",
            "children": [_predicate_to_dict(pred.children[0])],
        }
    # Leaf kinds: eq, ne, in, exists, missing.
    result: dict[str, Any] = {"kind": pred.kind}
    if pred.port is not None:
        port_d: dict[str, Any] = {"name": pred.port.name}
        if pred.port.field is not None:
            port_d["field"] = pred.port.field
        result["port"] = port_d
    if pred.value is not None:
        result["value"] = pred.value
    return result


def _io_schema_to_dict(schema: NodeIOSchema) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if schema.inputs:
        d["inputs"] = [_port_spec_to_dict(p) for p in schema.inputs]
    if schema.outputs:
        d["outputs"] = [_port_spec_to_dict(p) for p in schema.outputs]
    if schema.terminal_predicate is not None:
        d["terminal_predicate"] = _predicate_to_dict(schema.terminal_predicate)
    return d


def _port_spec_to_dict(spec: PortSpec) -> dict[str, Any]:
    d: dict[str, Any] = {"name": spec.name}
    if not spec.required:
        d["required"] = False
    if spec.payload_type is not None:
        # payload_type may be a BaseModel subclass; store its qualified name.
        t = spec.payload_type
        d["payload_type"] = f"{t.__module__}.{t.__qualname__}"
    return d


def _node_to_dict(n: PlanNode) -> dict[str, Any]:
    d: dict[str, Any] = {"id": n.id, "binding": n.binding.value}
    if n.io_schema.inputs or n.io_schema.outputs or n.io_schema.terminal_predicate:
        d["io_schema"] = _io_schema_to_dict(n.io_schema)
    if n.max_visits != 1:
        d["max_visits"] = n.max_visits
    if n.terminal:
        d["terminal"] = True
    if n.entry:
        d["entry"] = True
    if n.subgraph_ref is not None:
        d["subgraph_ref"] = {
            "plan_ref": n.subgraph_ref.plan_ref,
            "entry_node": n.subgraph_ref.entry_node,
            "binding_edge": n.subgraph_ref.binding_edge,
            "return_on": n.subgraph_ref.return_on,
        }
    for k, v in n.config.items():
        if k not in _PLAN_NODE_FIELDS:
            d[k] = v
    return d


def _edge_to_dict(e: PlanEdge) -> dict[str, Any]:
    d: dict[str, Any] = {"from": e.source, "to": e.target}
    if isinstance(e.when, Predicate):
        d["when"] = _predicate_to_dict(e.when)
    else:
        d["when"] = str(e.when) if e.when != "true" else "true"
    if e.subgraph_ref is not None:
        d["subgraph_ref"] = {
            "plan_ref": e.subgraph_ref.plan_ref,
            "entry_node": e.subgraph_ref.entry_node,
            "binding_edge": e.subgraph_ref.binding_edge,
            "return_on": e.subgraph_ref.return_on,
        }
    return d


def serialize_plan(p: Plan) -> str:
    """Serialize a :class:`Plan` to YAML (v2 BundleGraphSpec format)."""
    doc: dict[str, Any] = {"id": p.id}
    doc["nodes"] = [_node_to_dict(n) for n in p.nodes]
    if p.edges:
        doc["edges"] = [_edge_to_dict(e) for e in p.edges]
    if p.approval_resume_node is not None:
        doc["approval_resume_node"] = p.approval_resume_node
    return yaml.dump(doc, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Parsing: YAML → Plan (preserves typed Predicate on when)
# ---------------------------------------------------------------------------


def _parse_predicate(raw: Any) -> Predicate:
    """Parse a structured-predicate dict into a :class:`Predicate`."""
    if isinstance(raw, Predicate):
        return raw
    if isinstance(raw, str):
        # Legacy string when clause — wrap as exists(True) placeholder.
        return Predicate(kind="exists", value=True)
    if not isinstance(raw, Mapping):
        raise PlanLiftError(f"predicate must be a mapping or string, got {type(raw).__name__}")
    kind = raw["kind"]
    if kind in ("and", "or"):
        children = tuple(_parse_predicate(c) for c in raw.get("children", ()))
        return Predicate(kind=kind, children=children)
    if kind == "not":
        kids = raw.get("children", [])
        return Predicate(kind="not", children=(_parse_predicate(kids[0]),))
    # Leaf kinds.
    port_raw = raw.get("port")
    port_ref: PortRef | None = None
    if isinstance(port_raw, Mapping):
        port_ref = PortRef(
            name=port_raw["name"],
            field=port_raw.get("field"),
        )
    elif isinstance(port_raw, PortRef):
        port_ref = port_raw
    return Predicate(
        kind=kind,
        port=port_ref,
        value=raw.get("value"),
    )


def _parse_port_specs(raw: Any) -> tuple[PortSpec, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Sequence):
        return ()
    out: list[PortSpec] = []
    for item in raw:
        if isinstance(item, str):
            out.append(PortSpec(name=item))
        elif isinstance(item, Mapping):
            out.append(
                PortSpec(
                    name=item["name"],
                    required=item.get("required", True),
                    payload_type=None,  # string names only in YAML
                )
            )
    return tuple(out)


def _parse_io_schema(raw: Any) -> NodeIOSchema:
    if raw is None:
        return NodeIOSchema()
    if isinstance(raw, NodeIOSchema):
        return raw
    if not isinstance(raw, Mapping):
        return NodeIOSchema()
    tp_raw = raw.get("terminal_predicate")
    return NodeIOSchema(
        inputs=_parse_port_specs(raw.get("inputs")),
        outputs=_parse_port_specs(raw.get("outputs")),
        terminal_predicate=_parse_predicate(tp_raw) if tp_raw is not None else None,
    )


def _parse_subgraph_ref(raw: Any) -> SubgraphReference | None:
    if raw is None:
        return None
    if isinstance(raw, SubgraphReference):
        return raw
    if isinstance(raw, Mapping):
        return SubgraphReference(
            plan_ref=str(raw["plan_ref"]),
            entry_node=str(raw["entry_node"]),
            binding_edge=str(raw["binding_edge"]),
            return_on=str(raw.get("return_on", "next")),
        )
    return None


def _parse_plan_node(raw: Mapping[str, Any]) -> PlanNode:
    nid = str(raw["id"])
    binding_raw = raw.get("binding", "node_executor")
    binding = BindingKind(binding_raw) if isinstance(binding_raw, str) else binding_raw

    # io_schema from explicit key, or legacy inputs/outputs lists at top level.
    if "io_schema" in raw:
        io_schema = _parse_io_schema(raw["io_schema"])
    else:
        io_schema = NodeIOSchema(
            inputs=_parse_port_specs(raw.get("inputs")),
            outputs=_parse_port_specs(raw.get("outputs")),
        )

    config = {k: v for k, v in raw.items() if k not in _PLAN_NODE_FIELDS}

    return PlanNode(
        id=nid,
        binding=binding,
        io_schema=io_schema,
        config=config,
        max_visits=int(raw.get("max_visits", 1)),
        terminal=bool(raw.get("terminal", False)),
        entry=bool(raw.get("entry", False)),
        subgraph_ref=_parse_subgraph_ref(raw.get("subgraph_ref")),
    )


def _parse_plan_edge(raw: Mapping[str, Any]) -> PlanEdge:
    source = str(raw.get("from") or raw.get("source", ""))
    target = str(raw.get("to") or raw.get("target", ""))
    when_raw = raw.get("when")
    when: Predicate | str
    if isinstance(when_raw, Predicate):
        when = when_raw
    elif isinstance(when_raw, Mapping):
        when = _parse_predicate(when_raw)
    else:
        when = str(when_raw) if when_raw is not None else "true"
    return PlanEdge(
        source=source,
        target=target,
        when=when,
        subgraph_ref=_parse_subgraph_ref(raw.get("subgraph_ref")),
    )


def parse_plan_yaml(text: str) -> Plan:
    """Parse YAML into a :class:`Plan`, preserving typed Predicate on edges.

    Complements :func:`lift_graph_spec` (which stores ``when`` as a
    string) by keeping the structured :class:`Predicate` objects.
    """
    raw = yaml.safe_load(text)
    if not isinstance(raw, Mapping):
        raise PlanLiftError("plan YAML must be a mapping at the top level")

    nodes = tuple(_parse_plan_node(n) for n in raw.get("nodes", ()))
    edges = tuple(_parse_plan_edge(e) for e in raw.get("edges", ()))

    return Plan(
        id=str(raw.get("id", "")),
        nodes=nodes,
        edges=edges,
        approval_resume_node=raw.get("approval_resume_node"),
    )


__all__ = [
    "and_",
    "edge",
    "eq",
    "exists",
    "in_",
    "missing",
    "ne",
    "node",
    "not_",
    "or_",
    "parse_plan_yaml",
    "plan",
    "port",
    "routing",
    "serialize_plan",
]
