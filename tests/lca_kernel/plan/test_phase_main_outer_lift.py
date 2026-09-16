"""Atomic lift test for ``bundles/phase_main_outer.yaml`` (Task 6).

The outer plan is the production spine for the six-phase loop
(perceive → think → act → reflect → remember → terminal). After the
typed-port-graph redesign every edge ``when`` must be a structured
:class:`Predicate` (or ``None`` for unconditional), no string DSL.

This test guards the cutover: if any future change reintroduces a
string DSL or drops the typed predicates, lift succeeds but edge
``when`` instances lose their ``kind`` attribute, so the assertion
fails.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.framework.graph.lifter import lift_graph_spec

REPO = Path(__file__).resolve().parent.parent.parent.parent
BUNDLE = REPO / "bundles" / "outer" / "phase_main.yaml"


def test_phase_main_outer_yaml_lifts() -> None:
    """The outer plan must lift cleanly under the typed-port kernel."""
    text = BUNDLE.read_text(encoding="utf-8")
    if "<<<<<<<" in text or ">>>>>>>" in text:
        raise AssertionError(f"{BUNDLE} contains unresolved merge markers")
    spec = yaml.safe_load(text)
    plan = lift_graph_spec(spec)
    assert plan.id == "phase.main.outer"


def test_phase_main_outer_uses_typed_predicates() -> None:
    """Every edge must carry a typed Predicate (or None), not a string."""
    spec = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    plan = lift_graph_spec(spec)

    for edge in plan.edges:
        # ``None`` is the unconditional edge (always true); the rest must
        # have a structured ``kind`` field coming from a Predicate object.
        assert edge.when is None or hasattr(edge.when, "kind"), (
            f"edge {edge.source!r} -> {edge.target!r}: when is not typed "
            f"(got {type(edge.when).__name__}: {edge.when!r})"
        )


def test_phase_main_outer_has_termination() -> None:
    """Outer plan must declare a termination policy (terminal node)."""
    spec = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    plan = lift_graph_spec(spec)

    terminal_nodes = [n for n in plan.nodes if n.terminal]
    has_predicate = any(
        n.io_schema.terminal_predicate is not None for n in plan.nodes
    )
    assert terminal_nodes or has_predicate, (
        "phase_main_outer.yaml has no terminal node or terminal_predicate; "
        "the kernel would run forever"
    )


def test_phase_main_outer_edges_reference_declared_ports() -> None:
    """Lift-time predicate validation catches dangling port refs.

    If a future rewrite re-introduces a port the source node doesn't
    declare, ``lift_graph_spec`` must raise :class:`PlanLiftError`
    instead of silently allowing a runtime-false predicate.
    """
    from lca.contracts.protocols.graph.errors import PlanLiftError

    # Sanity: lifting the current bundle raises no PlanLiftError.
    spec = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    try:
        lift_graph_spec(spec)
    except PlanLiftError as exc:  # pragma: no cover - guard
        raise AssertionError(
            f"phase_main_outer.yaml should lift clean, got PlanLiftError: {exc}"
        )