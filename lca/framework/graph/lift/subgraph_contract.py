"""Subgraph port-contract checks and inner-plan loading at lift time.

Deep module behind :mod:`lca.framework.graph.lift.interface`.
"""
from __future__ import annotations

from pathlib import Path

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, SubgraphReference


def repo_root() -> Path:
    """Find the repo root by walking up from this package."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "bundles").is_dir():
            return parent
    return Path.cwd()


def bundle_yaml_path(plan_ref: str) -> Path:
    """Resolve a bundle-relative ``plan_ref`` to a filesystem path.

    Mirrors ``subgraph_run.repo_root`` so the lifter can read
    inner plans at lift time without importing the strategy module
    (avoids a circular import).
    """
    return repo_root() / plan_ref


def subgraph_entry_schema(
    subgraph_ref: SubgraphReference | None,
) -> NodeIOSchema:
    """Return the inner entry node's :class:`NodeIOSchema` for a subgraph
    delegate, or an empty schema when no delegate is wired.

    Loading the inner plan is best-effort: tests and dry lifts may
    pass :class:`ExecutablePlan` shims whose ``plan_ref`` paths do
    not resolve. On failure, the outer node carries an empty schema
    (current behavior) so existing tests keep passing.
    """
    if subgraph_ref is None:
        return NodeIOSchema()
    try:
        import yaml

        from lca.framework.graph.lift.graph_spec import lift_graph_spec_inner

        path = bundle_yaml_path(subgraph_ref.plan_ref)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return NodeIOSchema()
        spec = dict(raw)
        if "entry" not in spec and subgraph_ref.entry_node:
            spec["entry"] = subgraph_ref.entry_node
        inner_plan = lift_graph_spec_inner(spec)
        return inner_plan.node(subgraph_ref.entry_node).io_schema
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return NodeIOSchema()


def require_subgraph_plan_exists(
    spec_id: str, node_id: str, subgraph_ref: SubgraphReference
) -> None:
    """Raise :class:`PlanLiftError` if *subgraph_ref.plan_ref* points nowhere.

    Subgraph delegates whose target file is missing or unreadable
    silently degrade today (``subgraph_entry_schema`` returns an
    empty schema on load failure, leaving the outer node with no
    inputs / no outputs and the kernel crashing at first dispatch).
    Catching this at lift time surfaces a structured boot error so
    the operator sees the wrong ``plan_ref`` next to the wrong node.
    """
    try:
        path = bundle_yaml_path(subgraph_ref.plan_ref)
    except (OSError, ValueError) as exc:
        raise PlanLiftError(
            f"plan {spec_id!r}: subgraph node {node_id!r} plan_ref "
            f"{subgraph_ref.plan_ref!r} failed to resolve: {exc}",
            plan_id=spec_id,
            node_id=node_id,
        ) from exc
    if not path.exists():
        raise PlanLiftError(
            f"plan {spec_id!r}: subgraph node {node_id!r} plan_ref "
            f"{subgraph_ref.plan_ref!r} does not exist (resolved path={path})",
            plan_id=spec_id,
            node_id=node_id,
        )


def enforce_subgraph_port_contract(
    *,
    spec_id: str,
    node_id: str,
    outer_schema: NodeIOSchema,
    subgraph_ref: SubgraphReference,
    declared_inputs_present: bool,
    declared_outputs_present: bool,
) -> None:
    """Reject subgraph ``declared_inputs/outputs`` names the inner plan can't honor.

    The subgraph data contract (ADR-0217 §3.3.3) is **name-based**:
    :class:`SubgraphStrategy` reads ``outer_schema.outputs`` by name
    from the merged inner output dict, and the inner kernel reads
    ``inner_schema.inputs`` by name from the outer port registry.
    A name that exists on one side but not the other causes a
    silent drop at runtime (``merged_output[outer_name]`` is
    ``None`` / not-present, or the inner reads a name it never
    received).

    Lift-time rejection turns this into a boot-time failure with
    structured context so the operator fixes the bundle.

    Inputs contract: every name in ``outer_schema.inputs`` must
    exist in the union of inputs declared on any inner plan node
    reachable from the entry.

    Outputs contract: every name in ``outer_schema.outputs`` must
    exist in the union of outputs declared on any inner plan node
    reachable from the entry. The subgraph entry node itself may
    only declare a subset; downstream inner nodes produce the
    rest and merge into the outer output dict.

    Falls through silently when the inner plan cannot be loaded
    (``require_subgraph_plan_exists`` already raised a structured
    error in that case; duplicating it here would just produce
    noise).
    """
    inner_plan = load_subgraph_plan_for_contract(subgraph_ref)
    if inner_plan is None:
        return
    if declared_inputs_present:
        inner_in_names: set[str] = set()
        for n in inner_plan.nodes:
            inner_in_names |= {p.name for p in n.io_schema.inputs}
        unknown = [p.name for p in outer_schema.inputs if p.name not in inner_in_names]
        if unknown:
            raise PlanLiftError(
                f"plan {spec_id!r}: subgraph node {node_id!r} declared_inputs "
                f"{unknown!r} are not declared by any inner plan node; "
                f"the inner kernel cannot read them. inner_declared_inputs="
                f"{sorted(inner_in_names)}",
                plan_id=spec_id,
                node_id=node_id,
            )
    if declared_outputs_present:
        inner_out_names: set[str] = set()
        for n in inner_plan.nodes:
            inner_out_names |= n.io_schema.output_names()
        unknown = [p.name for p in outer_schema.outputs if p.name not in inner_out_names]
        if unknown:
            raise PlanLiftError(
                f"plan {spec_id!r}: subgraph node {node_id!r} declared_outputs "
                f"{unknown!r} are not produced by any inner plan node; "
                f"the subgraph will never emit them. inner_declared_outputs="
                f"{sorted(inner_out_names)}",
                plan_id=spec_id,
                node_id=node_id,
            )


def load_subgraph_plan_for_contract(
    subgraph_ref: SubgraphReference,
) -> Plan | None:
    """Load the inner plan referenced by *subgraph_ref* for contract checks.

    Returns ``None`` when the plan cannot be loaded (missing file,
    malformed yaml, missing entry node). The contract check is
    best-effort; the inner-plan lift error gets surfaced
    separately by the boot-time ``plan_validation`` aggregator.
    """
    try:
        import yaml

        from lca.framework.graph.lift.graph_spec import lift_graph_spec_inner

        path = bundle_yaml_path(subgraph_ref.plan_ref)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        spec = dict(raw)
        if "entry" not in spec and subgraph_ref.entry_node:
            spec["entry"] = subgraph_ref.entry_node
        return lift_graph_spec_inner(spec)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return None


# Backward-compatible private aliases.
_bundle_yaml_path = bundle_yaml_path
_subgraph_entry_schema = subgraph_entry_schema
_require_subgraph_plan_exists = require_subgraph_plan_exists
_enforce_subgraph_port_contract = enforce_subgraph_port_contract
_load_subgraph_plan_for_contract = load_subgraph_plan_for_contract

__all__ = [
    "bundle_yaml_path",
    "enforce_subgraph_port_contract",
    "load_subgraph_plan_for_contract",
    "repo_root",
    "require_subgraph_plan_exists",
    "subgraph_entry_schema",
]
