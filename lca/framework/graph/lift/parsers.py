"""YAML/DTO parsers for the plan lift seam.

Deep module behind :mod:`lca.framework.graph.lift.interface`. Callers
outside the lift package should go through :func:`lift_graph_spec` /
:class:`PlanLifter` rather than importing these helpers.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import SubgraphReference
from lca.contracts.protocols.graph.predicate import PortRef, Predicate

_LEAF_PREDICATE_KINDS = frozenset({"eq", "ne", "in", "exists", "missing"})


def binding_from(value: object) -> BindingKind:
    if isinstance(value, BindingKind):
        return value
    if isinstance(value, str):
        try:
            return BindingKind(value)
        except ValueError:
            if value.startswith("concept."):
                return BindingKind.NODE_EXECUTOR
            raise ValueError(
                f"binding must be a BindingKind or string, got {value!r}"
            ) from None
    raise ValueError(f"binding must be a BindingKind or string, got {type(value).__name__}")


def binding_from_factory_or_binding(raw: Mapping[str, object]) -> BindingKind:
    """Pick the right binding for a BundleGraphSpec-style node.

    Three inputs in priority order:

    1. ``binding:`` — explicit :class:`BindingKind` (v2 schema).
    2. ``sub_spec_ref:`` — nested subgraph; the kernel recurses via
       :class:`SubgraphStrategy`. Legacy think/act yaml nests
       ``sub_spec_ref:`` under ``config:``, so check both surfaces.
       Wins over ``factory`` so a node like ``think.reason``
       (sub-spec only) recurses instead of dispatching a leaf
       executor that does not exist.
    3. ``factory:`` — legacy think/act subgraph style; ``factory:
       think.*`` / ``factory: act.*`` map to
       :class:`BindingKind.NODE_EXECUTOR` so the kernel can dispatch
       them via :class:`NodeExecutorStrategy`.
    """
    binding = raw.get("binding")
    if binding is not None:
        return binding_from(binding)
    if raw.get("sub_spec_ref") is not None:
        return BindingKind.SUBGRAPH
    config = raw.get("config")
    if isinstance(config, Mapping) and config.get("sub_spec_ref") is not None:
        return BindingKind.SUBGRAPH
    factory = raw.get("factory")
    if factory is None:
        raise ValueError(
            "node spec must declare either 'binding' or 'factory'; "
            f"got neither in node keys={sorted(raw)}"
        )
    return BindingKind.NODE_EXECUTOR


def binding_for_phase_node(raw: object) -> BindingKind:
    sub_ref = getattr(raw, "sub_spec_ref", None)
    binding_attr = getattr(raw, "binding", None)
    if sub_ref is not None:
        return BindingKind.SUBGRAPH
    if binding_attr is None:
        return BindingKind.TRANSFORM
    return binding_from(binding_attr)


def schema_from(inputs: object, outputs: object) -> NodeIOSchema:
    """Build a :class:`NodeIOSchema` from yaml ``inputs``/``outputs`` declarations.

    Inputs and outputs are independent port namespaces. A name
    that appears on both sides is a **read+write alias** (e.g. an
    act subgraph reads ``decision`` from upstream and emits a
    stamped ``decision`` downstream) — :class:`NodeIOSchema`
    permits this within the schema-level uniqueness invariant
    (uniqueness is per-direction). Both sides are preserved so the
    lifter records the full emit/read contract, the kernel
    forwards a same-named upstream value into the subgraph via
    :class:`SubgraphStrategy`, and downstream wiring checks see
    the emitted port on the output side.
    """
    in_specs = to_port_specs(inputs)
    out_specs = to_port_specs(outputs)
    return NodeIOSchema(inputs=in_specs, outputs=out_specs)


def to_port_specs(names: object) -> tuple[PortSpec, ...]:
    """Coerce yaml port lists — bare strings or ``{name, required?}`` dicts."""
    if names is None:
        return ()
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, (list, tuple)):
        return ()
    out: list[PortSpec] = []
    for item in names:
        if isinstance(item, str):
            if not item:
                continue
            try:
                out.append(PortSpec(name=item))
            except Exception:  # noqa: S112
                continue
        elif isinstance(item, Mapping):
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            try:
                out.append(
                    PortSpec(
                        name=name,
                        required=bool(item.get("required", True)),
                        payload_type=None,  # YAML cannot carry live types
                    )
                )
            except Exception:  # noqa: S112
                continue
    return tuple(out)


def io_schema_from_mapping(raw: Mapping[str, Any]) -> NodeIOSchema:
    """Build :class:`NodeIOSchema` from an SDK-serialized ``io_schema`` mapping."""
    tp_raw = raw.get("terminal_predicate")
    return NodeIOSchema(
        inputs=to_port_specs(raw.get("inputs")),
        outputs=to_port_specs(raw.get("outputs")),
        terminal_predicate=coerce_when(tp_raw) if tp_raw is not None else None,
    )


def subgraph_ref_from(raw: object) -> SubgraphReference | None:
    if raw is None:
        return None
    if isinstance(raw, SubgraphReference):
        return raw
    if isinstance(raw, Mapping):
        return SubgraphReference(
            plan_ref=str(raw.get("plan_ref", "")),
            entry_node=str(raw.get("entry_node", "")),
            binding_edge=str(raw.get("binding_edge", "")),
            return_on=str(raw.get("return_on", "next")),
        )
    # Legacy typed dataclass: ``PhaseNode.sub_spec_ref`` (ADR-0217 §3) is
    # a frozen dataclass with the same four fields as the new
    # ``SubgraphReference``. Read attributes directly.
    plan_ref = getattr(raw, "plan_ref", None)
    if plan_ref is None:
        return None
    return SubgraphReference(
        plan_ref=str(plan_ref),
        entry_node=str(getattr(raw, "entry_node", "") or ""),
        binding_edge=str(getattr(raw, "binding_edge", "") or ""),
        return_on=str(getattr(raw, "return_on", "next") or "next"),
    )


def coerce_when(raw: object) -> Predicate | None:
    """Coerce a YAML ``when`` value to :class:`Predicate` or ``None``.

    - ``None`` / ``True`` / ``"true"`` / ``""`` → ``None`` (unconditional)
    - :class:`Predicate` → pass-through
    - dict with ``kind`` → structured Predicate (D6 plan SDK path)
    - any other string → ``PlanLiftError``. The legacy string-DSL
      edge conditions silently evaluated to ``False`` and were the
      root cause of ``outcome=failure`` runs (see spec §0). The D4
      cutover rejects every string at lift time so a misroute never
      reaches runtime.
    """
    if raw is None:
        return None
    if isinstance(raw, Predicate):
        return raw
    if isinstance(raw, bool):
        return (
            None
            if raw
            else Predicate(
                kind="eq",
                port=PortRef(name="__never__"),
                value=True,
            )
        )
    if isinstance(raw, Mapping):
        return parse_predicate_dict(raw)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in ("true", "false", "none", ""):
            return None
        raise PlanLiftError(
            f"string `when: {raw!r}` is no longer supported; "
            "use a typed Predicate dict (see ADR-0195 typed-port graph)",
        )
    return None


def parse_predicate_dict(raw: Mapping[str, Any]) -> Predicate:
    """Parse a dict-shaped predicate into a :class:`Predicate`."""
    kind = str(raw.get("kind", ""))
    if not kind:
        raise PlanLiftError("predicate dict missing 'kind' field")
    bool_kinds = frozenset({"and", "or", "not"})
    if kind in bool_kinds:
        children_raw = raw.get("children", ())
        if not isinstance(children_raw, (list, tuple)):
            raise PlanLiftError(f"predicate kind={kind!r}: children must be a sequence")
        children = tuple(c for c in (coerce_when(c) for c in children_raw) if c is not None)
        return Predicate(kind=kind, children=children)
    if kind in _LEAF_PREDICATE_KINDS:
        port_raw = raw.get("port")
        port = parse_port_ref(port_raw) if port_raw is not None else None
        value = raw.get("value")
        return Predicate(kind=kind, port=port, value=value)
    raise PlanLiftError(f"unknown predicate kind: {kind!r}")


def parse_port_ref(raw: object) -> PortRef:
    """Parse a ``port`` dict into a :class:`PortRef`."""
    if isinstance(raw, PortRef):
        return raw
    if isinstance(raw, Mapping):
        name = str(raw.get("name", ""))
        field = raw.get("field")
        return PortRef(name=name, field=str(field) if field is not None else None)
    raise PlanLiftError(f"port ref must be a dict or PortRef, got {type(raw).__name__}")


# Backward-compatible private aliases used by legacy call sites / tests.
_binding_from = binding_from
_binding_from_factory_or_binding = binding_from_factory_or_binding
_binding_for_phase_node = binding_for_phase_node
_schema_from = schema_from
_to_port_specs = to_port_specs
_subgraph_ref_from = subgraph_ref_from
_coerce_when = coerce_when
_parse_predicate_dict = parse_predicate_dict
_parse_port_ref = parse_port_ref

__all__ = [
    "_LEAF_PREDICATE_KINDS",
    "binding_for_phase_node",
    "binding_from",
    "binding_from_factory_or_binding",
    "coerce_when",
    "io_schema_from_mapping",
    "parse_port_ref",
    "parse_predicate_dict",
    "schema_from",
    "subgraph_ref_from",
    "to_port_specs",
]
