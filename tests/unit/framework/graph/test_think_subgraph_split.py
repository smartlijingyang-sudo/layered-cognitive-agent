"""Spec §E: think.reason.complete is split into three single-responsibility nodes.

The think subgraph must contain:
- ``think.history.assemble`` (added by Task 2)
- ``llm.invoke`` + ``llm.persist`` (PR-B typed-port cutover split the
  Task 3 ``think.llm.dispatch`` node into an adapter-call node and a
  journal-write node)
- ``think.decision.parse`` (added by Task 3)

``think.reason.complete`` is removed in Task 4; this test asserts its
absence from ``bundles/think.yaml`` once Task 3 lands.

``think_subgraph.yaml`` is normally loaded as a subgraph from
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
    """Load ``bundles/think/think_subgraph.yaml`` and lift it with an injected entry node.

    Mirrors ``_subgraph_entry_schema``'s entry injection so the standalone
    think_subgraph.yaml lifts cleanly. The production load path goes through
    ``phase_main.yaml`` which carries the entry_node.
    """
    repo_root = Path(__file__).resolve().parents[4]
    spec = yaml.safe_load(
        (repo_root / "bundles" / "think" / "think_subgraph.yaml").read_text(encoding="utf-8")
    )
    if "entry" not in spec:
        spec = {**spec, "entry": _THINK_ENTRY_NODE}
    return lift_graph_spec(spec)


def test_think_subgraph_has_three_nodes() -> None:
    """think_subgraph must contain history.assemble, the llm split, decision.parse."""
    plan = _lifted_think_plan()
    node_ids = {n.id for n in plan.nodes}
    assert "think.history.assemble" in node_ids
    assert "llm.invoke" in node_ids
    assert "llm.persist" in node_ids
    # PR-B split think.llm.dispatch into llm.invoke + llm.persist; the
    # pre-split node id must not resurface in the think subgraph.
    assert "think.llm.dispatch" not in node_ids
    assert "think.decision.parse" in node_ids
    # think.reason.complete lives in bundles/think_reason.yaml; the
    # outer think.yaml must not redeclare it once Task 3 lands.
    assert "think.reason.complete" not in node_ids


def test_think_subgraph_wires_history_to_llm_to_decision() -> None:
    """The new edges route history.assemble → llm.invoke → llm.persist → decision.parse."""
    plan = _lifted_think_plan()
    edges_by_pair = {(e.source, e.target) for e in plan.edges}
    assert ("think.history.assemble", "llm.invoke") in edges_by_pair
    assert ("llm.invoke", "llm.persist") in edges_by_pair
    assert ("llm.persist", "think.decision.parse") in edges_by_pair
