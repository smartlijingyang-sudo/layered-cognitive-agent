"""Regression guard for the v2 graph predicate + select_edge seam (D4).

The v2 traversal's `select_edge` reads typed :class:`Predicate` objects
through :func:`evaluate_predicate` and :class:`PortReader`. This test
drives the real typed evaluator against the actual
`bundles/outer/phase_main.yaml` plan after the D4 bundle rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.lifter import lift_graph_spec
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.predicate_evaluator import evaluate_predicate
from lca.framework.graph.traversal import select_edge


@pytest.fixture(scope="module")
def outer_plan():
    spec = yaml.safe_load(Path("bundles/outer/phase_main.yaml").read_text(encoding="utf-8"))
    return lift_graph_spec(spec)


def test_all_edges_have_typed_predicates(outer_plan) -> None:
    """After D4, every edge's `when` must be a Predicate or None."""
    for edge in outer_plan.edges:
        assert edge.when is None or isinstance(edge.when, Predicate), (
            f"edge {edge.source} → {edge.target}: "
            f"when must be Predicate | None, got {type(edge.when).__name__}"
        )


def test_predicate_typed_eq_evaluation() -> None:
    """Typed predicate eq evaluation works through PortReader."""
    from lca.contracts.atoms.enums.enums import ActionType
    from lca.contracts.protocols.graph.routing import RoutingDecision

    reg = PortRegistry()
    reg.set_typed_port(
        "routing",
        RoutingDecision(action_type=ActionType.USE_TOOL),
        payload_type=RoutingDecision,
    )
    reader = PortReader(source_node="think.main", registry=reg)
    pred = Predicate(
        kind="eq",
        port=PortRef(name="routing", field="action_type"),
        value=ActionType.USE_TOOL,
    )
    assert evaluate_predicate(pred, reader=reader) is True


def test_select_edge_picks_think_after_successful_perceive(outer_plan) -> None:
    """After a successful perceive visit, the traversal must advance to
    `think.main` (unconditional edge: when=None)."""
    outgoing = tuple(e for e in outer_plan.edges if e.source == "perceive.main")
    assert outgoing, "outer plan must declare perceive.main edges"

    reg = PortRegistry()
    reg.merge_output({"perceive_payload": {"manifest": "ok"}})

    chosen = select_edge(
        edges=outgoing,
        current_id="perceive.main",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is not None, (
        "select_edge must pick the next phase after perceive; "
        "returning None means the traversal terminates after one visit"
    )
    assert chosen.target == "think.main"


def test_act_main_routes_failed_tool_back_to_think(outer_plan) -> None:
    """A USE_TOOL decision whose effect failed loops back to `think.main`.

    Regression for run_eed09c1df112: the sandbox reported
    ``ModuleNotFoundError: No module named 'pdf2image'`` at step 4,
    ``act.observe.terminate_decide`` emitted ``should_terminate=True``, and
    these edges sent the run to ``terminal.commit`` — the model never got the
    turn it needed to install the package or switch to another tool. Only an
    unclassified (host-side dispatch) failure may take the terminal edge now.
    """
    from lca.contracts.atoms.enums.enums import ActionType
    from lca.contracts.models.core.execution.decision import Decision
    from lca.contracts.protocols.graph.routing import RoutingDecision

    outgoing = tuple(e for e in outer_plan.edges if e.source == "act.main")
    assert outgoing, "outer plan must declare act.main edges"

    def _choose(should_terminate: bool):
        reg = PortRegistry()
        reg.merge_output(
            {
                "decision": Decision(
                    decision_id="decision_de1c7d99a59a",
                    action_type="use_tool",
                    rationale="extract the pdf",
                    confidence=1.0,
                ),
                "approval_routing": RoutingDecision(
                    action_type=ActionType.USE_TOOL, next_hint="approve_skipped"
                ),
                "should_terminate": should_terminate,
            }
        )
        return select_edge(
            edges=outgoing,
            current_id="act.main",
            reader_factory=lambda src: PortReader(source_node=src, registry=reg),
        )

    assert _choose(should_terminate=False).target == "think.main"
    assert _choose(should_terminate=True).target == "terminal.commit"


def test_select_edge_no_match_when_port_unset() -> None:
    """An edge with a predicate referencing an unset port does not match."""
    from lca.contracts.protocols.graph.plan import PlanEdge

    edge = PlanEdge(
        source="a",
        target="b",
        when=Predicate(kind="eq", port=PortRef(name="routing", field="action_type"), value="x"),
    )
    reg = PortRegistry()
    chosen = select_edge(
        edges=(edge,),
        current_id="a",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is None
