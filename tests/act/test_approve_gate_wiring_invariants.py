"""PR-1 regression guards for act HITL wiring.

Two defects found while executing PR-1 and fixed before merge:

1. **Factory-less delegate nodes** — ``bundles/act/act_subgraph.yaml`` is
   loaded by ``_load_bundle_graph_spec``, which reads ``factory`` for every
   node (unlike the outer plan, which is loaded by ``plan_sdk.parse_plan_yaml``
   and defaults ``binding`` to ``node_executor``). Declaring an outer or
   sibling node (``intervene.interrupt``, ``intervene.resume``,
   ``terminal.commit``) inside the act subgraph therefore crashes
   ``lca-ops plan tree`` with ``KeyError: 'factory'``. A subgraph must not
   name another plan's nodes.

2. **Disconnected HITL island** — relocating the gate's executor into the
   act subgraph while leaving the outer ``act.approve.gate`` delegate in
   place removed every edge into and out of that delegate. Only
   ``intervene.resume → act.approve.gate`` survived, so an interrupt could
   never be reached and a rejected approval could never abort. The gate must
   stay reachable from ``act.main`` and keep its three outgoing routes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTER_PLAN = REPO_ROOT / "bundles" / "outer" / "phase_main.yaml"
ACT_SUBGRAPH = REPO_ROOT / "bundles" / "act" / "act_subgraph.yaml"


def _nodes(path: Path) -> dict[str, dict[str, object]]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {node["id"]: node for node in spec["nodes"]}


def _edges(path: Path) -> set[tuple[str, str]]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        (edge.get("from") or edge.get("source"), edge.get("to") or edge.get("target"))
        for edge in spec["edges"]
    }


def test_act_subgraph_nodes_all_declare_factory() -> None:
    """The BundleGraph loader requires ``factory`` on every act-subgraph node.

    Guards defect 1: a subgraph that borrows an outer node id lifts fine in
    ``plan_sdk`` but crashes the subgraph resolver.
    """
    offenders = [node_id for node_id, node in _nodes(ACT_SUBGRAPH).items() if "factory" not in node]
    assert not offenders, (
        f"act subgraph nodes without 'factory' break lca-ops plan tree: {offenders}"
    )


def test_act_subgraph_does_not_declare_foreign_nodes() -> None:
    """act_subgraph may only declare ``act.*`` nodes (plus its own effect refs).

    Guards the root cause of defect 1: ``intervene.*`` and ``terminal.commit``
    belong to the outer plan.
    """
    foreign = {
        node_id
        for node_id in _nodes(ACT_SUBGRAPH)
        if not node_id.startswith("act.") and not node_id.startswith("effect.")
    }
    assert not foreign, f"act subgraph declares nodes owned by other plans: {foreign}"


def test_outer_approve_gate_is_reachable_from_act_main() -> None:
    """Guards defect 2: the gate must have an inbound edge from ``act.main``.

    Without it the HITL gate can never fire, so a dangerous tool call
    reaches the effect gateway unapproved.
    """
    assert ("act.main", "act.approve.gate") in _edges(OUTER_PLAN)


def test_outer_approve_gate_has_all_three_routes() -> None:
    """The gate must be able to pause, abort, and continue.

    ``intervene.interrupt`` pauses for a human command, ``terminal.commit``
    aborts a rejected approval, and ``reflect.main`` continues after an
    approval or a no-approval-needed pass-through. Dropping any one of them
    silently dead-ends the HITL cycle.
    """
    edges = _edges(OUTER_PLAN)
    for target in ("intervene.interrupt", "terminal.commit", "reflect.main"):
        assert ("act.approve.gate", target) in edges, f"missing act.approve.gate → {target}"


def test_outer_approve_gate_keeps_resume_edge() -> None:
    """Resume must re-enter the gate so a persisted Command is consulted."""
    assert ("intervene.resume", "act.approve.gate") in _edges(OUTER_PLAN)


def test_gate_declared_in_exactly_one_plan() -> None:
    """The gate must not be declared in both the outer plan and act_subgraph.

    Two declarations means two HITL evaluations per run — the second would
    re-prompt for a decision already approved.
    """
    outer_has = "act.approve.gate" in _nodes(OUTER_PLAN)
    inner_has = "act.approve.gate" in _nodes(ACT_SUBGRAPH)
    assert outer_has != inner_has, (
        f"act.approve.gate declared in outer={outer_has} and "
        f"act_subgraph={inner_has}; exactly one may own it"
    )
