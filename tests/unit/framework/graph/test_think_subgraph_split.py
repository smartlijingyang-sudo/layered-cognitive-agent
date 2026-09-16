"""Spec §E: think.reason.complete is split into three single-responsibility nodes.

The think subgraph must contain:
- ``think.history.assemble`` (added by Task 2)
- ``think.llm.dispatch`` (added by Task 3)
- ``think.decision.parse`` (added by Task 3)

``think.reason.complete`` is removed in Task 4; this test asserts its
absence from ``bundles/think.yaml`` once Task 3 lands.

``think.yaml`` is normally loaded as a subgraph from
``bundles/outer/phase_main.yaml`` with an explicit ``entry_node``
injection; this test mirrors that injection (``think.shortcut`` is the
declared entry point in the outer file) so the lifter can produce a
:class:`Plan` for assertion.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.framework.graph.lifter import lift_graph_spec

_THINK_ENTRY_NODE = "think.shortcut"


def _lifted_think_plan() -> object:
    """Load ``bundles/think.yaml`` and lift it with an injected entry node.

    Mirrors ``_subgraph_entry_schema``'s entry injection so the standalone
    think.yaml lifts cleanly. The production load path goes through
    ``phase_main_outer.yaml`` which carries the entry_node.
    """
    repo_root = Path(__file__).resolve().parents[4]
    spec = yaml.safe_load((repo_root / "bundles" / "think.yaml").read_text(encoding="utf-8"))
    if "entry" not in spec:
        spec = {**spec, "entry": _THINK_ENTRY_NODE}
    return lift_graph_spec(spec)


def test_think_subgraph_has_three_nodes() -> None:
    """think_subgraph must contain history.assemble, llm.dispatch, decision.parse."""
    plan = _lifted_think_plan()
    node_ids = {n.id for n in plan.nodes}
    assert "think.history.assemble" in node_ids
    assert "think.llm.dispatch" in node_ids
    assert "think.decision.parse" in node_ids
    # think.reason.complete lives in bundles/think_reason.yaml; the
    # outer think.yaml must not redeclare it once Task 3 lands.
    assert "think.reason.complete" not in node_ids


def test_think_subgraph_wires_history_to_llm_to_decision() -> None:
    """The new edges route history.assemble → llm.dispatch → decision.parse."""
    plan = _lifted_think_plan()
    edges_by_pair = {(e.source, e.target) for e in plan.edges}
    assert ("think.history.assemble", "think.llm.dispatch") in edges_by_pair
    assert ("think.llm.dispatch", "think.decision.parse") in edges_by_pair
