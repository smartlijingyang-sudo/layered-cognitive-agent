"""Plan SDK — typed Python surface for constructing plan graphs.

Provides convenience builders over the contract-layer Pydantic types
(:class:`Plan`, :class:`PlanNode`, :class:`PlanEdge`, :class:`Predicate`,
:class:`PortRef`, :class:`RoutingDecision`). Every builder returns a
typed Pydantic model; no raw dicts leak through the public API.

Serialization produces YAML matching the v2 BundleGraphSpec shape
(structured ``when`` predicates, not string DSL). Parsing reverses
the process so ``parse_plan_yaml(serialize_plan(p))`` recovers the
same ``Plan`` with typed :class:`Predicate` objects on every edge.

Port name catalog (D5 mapping — each port name has one or more D4 consumers):
=============================================================================

The graph framework does NOT enforce a closed set of port names at the
type level. ``PortName`` is a ``NewType`` alias for ``str`` (see
``lca.contracts.protocols.declarative.declarative_1.ports``). Lift-time
validation ensures every referenced port exists in the node's IO schema.

This catalog documents the business port names used by the agent/cognition
domain. It lives here (SDK layer) rather than in the framework because
the framework is domain-agnostic. Adding a new business port name requires
updating this catalog and the D5 mapping in ``docs/adr/0219-phase-graph-unification.md`` §5.1.

Core cognition ports:
- ``decision``              think.decision.parse / think.gate  →  outer interpreter / act phase
- ``observation``           observation nodes           →  outer interpreter
- ``reflection``            reflect nodes               →  outer interpreter
- ``response``              think.llm.dispatch          →  think.decision.parse

Turn planning ports:
- ``turn_plan``             think.reason.plan           →  think.reason.render
- ``turn_render``           think.reason.render         →  think.llm.dispatch

Shortcut and routing ports:
- ``in_assembled_manifest`` think.shortcut / think.route →  outer loop
- ``route_choice``          think.route                 →  downstream
- ``enforced_state``        think.route                 →  Reducer / state fold

Decision subgraph ports:
- ``tool_calls``            decision.parse.response     →  decision.compose.action
- ``delegations``           decision.parse.response     →  decision.compose.action
- ``enforced_decision``     decision.enforce.chain_run  →  act subgraph
- ``intent``                decision.parse.response     →  decision.compose.action

Role snapshot ports:
- ``role``                  role_snapshot.normalize     →  role_snapshot.compose
- ``role_snapshot``         role_snapshot.compose       →  downstream

Context composition ports:
- ``context``               context_compose.skills      →  think.reason.render
- ``manifest``              context_compose.collect     →  think.reason.render
- ``context_items``         perceive_turn.fold          →  perceive consumers
- ``raw_inputs``            perceive_turn.collect       →  perceive consumers

Prompt rendering ports:
- ``prompt_text``           prompt_render.fill          →  prompt consumers
- ``prompt_trace``          prompt_render.fill          →  prompt consumers
- ``prompt_template``       prompt_render.assemble      →  prompt consumers
- ``render``                prompt_render.compile       →  prompt consumers

Template selection ports:
- ``template_selection``    template_select.pick        →  reasoner
- ``scored``                template_select.score       →  template_select.pick
- ``candidates``            template_select.enumerate   →  template_select.score

Action subgraph ports:
- ``forked_tools``          tool_fork.dispatch          →  act subgraph
- ``envelope``              act_subgraph.act_envelope   →  body / executor
- ``receipt``               effect_execute.execute      →  downstream
- ``memory_receipt``        memory_write.admit_policy / memory_write.dispatch → downstream

Stop policy ports:
- ``stop_decision``         stop.policy                 →  outer interpreter
- ``stop_payload``          stop.policy                 →  outer interpreter

Outer-flow-control port names (first-principle fix for the
``ContextManifest`` reflect bug; ``bundles/phase_main_outer.yaml``
declares these as ``declared_inputs``/``declared_outputs`` and the
kernel uses them as the typed projection between phase main subgraphs
— see ADR-0219 §5.1 + the kernel's :class:`SubgraphStrategy`
positional translation. Each has one writer (the upstream phase main)
and one reader (the next phase main):
- ``perceive_payload``      perceive.main   →  think.main
- ``act_outcome``           act.main        →  reflect.main
- ``reflect_outcome``       reflect.main    →  remember.main
- ``memory_record``         remember.main   →  stop.main

Historical (deleted, no D4 consumer — see ADR-0219 §7.2):
- ``think_signal``          retired 2026-09-10 (was think.gate invented field)
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
from lca.framework.graph.lift.interface import PlanLifter, get_plan_lifter

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
    terminal: bool = False,
    entry: bool = False,
    subgraph_ref: SubgraphReference | None = None,
    **config: Any,
) -> PlanNode:
    """Build a :class:`PlanNode` with typed IO schema and config extras.

    ADR-0225: ``max_visits`` kwarg removed. Per-node visit ceilings
    are no longer first-class on the v2 surface; termination is via
    ``terminal_predicate`` (per-node), ``Decision(action_type=respond)``
    from think, or :class:`AgentState.budget` ceilings.
    """
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
    """Build a :class:`Plan`.

    ``approval_resume_node`` 字段语义(PR-1 升级):
    - 当 plan 含 ``act.approve.gate`` 节点时,此字段 MUST 设置(值 = resume 边 target 节点 id)
    - 当 plan 不含 ``act.approve.gate`` 节点时,此字段 ignored(yaml 可省)
    - lifter 校验:``_validate_approval_resume_node(plan)`` 强制(Step 1.9)
    """
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
    # ADR-0225: per-node ``max_visits`` no longer serialized. Termination
    # surfaces via ``terminal_predicate`` on the io_schema (above) plus
    # the natural Decision/should_terminate paths in the kernel.
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
    elif e.when is None:
        d["when"] = "true"
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
# Parsing: YAML → Plan (via Lift interface — no duplicated parsers)
# ---------------------------------------------------------------------------


def lift_via_interface(spec: Mapping[str, Any], *, lifter: PlanLifter | None = None) -> Plan:
    """Lift a BundleGraphSpec / SDK-serialized mapping through :class:`PlanLifter`.

    plan_sdk produces Plan from YAML-like structures only through this
    seam (predicate + termination validation included). Do not
    re-implement lift parsers here.
    """
    return (lifter or get_plan_lifter()).lift_graph_spec(spec)


def parse_plan_yaml(text: str) -> Plan:
    """Parse YAML into a :class:`Plan` via the Lift interface.

    Complements :func:`serialize_plan`: ``parse_plan_yaml(serialize_plan(p))``
    recovers the same :class:`Plan` with typed :class:`Predicate` edges.
    Production validation (predicates + termination) runs inside
    :meth:`PlanLifter.lift_graph_spec`.
    """
    raw = yaml.safe_load(text)
    if not isinstance(raw, Mapping):
        raise PlanLiftError("plan YAML must be a mapping at the top level")
    return lift_via_interface(dict(raw))


__all__ = [
    "PlanLifter",
    "and_",
    "edge",
    "eq",
    "exists",
    "get_plan_lifter",
    "in_",
    "lift_via_interface",
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
