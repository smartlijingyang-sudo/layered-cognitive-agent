"""Tests for ADR-0244 PR-3: phase_main.yaml outer topology closed-loop.

Verifies that:
1. When think.main produces `respond`, it routes to `reflect.main` (NOT terminal.commit);
2. When act.main completes with `should_terminate=True`, it routes to `reflect.main` (NOT terminal.commit);
3. reflect.main routes to remember.main (or think.main on admit_recovery);
4. remember.main routes to terminal.commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.framework.graph.lifter import lift_graph_spec
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.traversal import select_edge


@pytest.fixture(scope="module")
def outer_plan():
    repo_root = Path(__file__).resolve().parents[3]
    spec = yaml.safe_load((repo_root / "bundles/outer/phase_main.yaml").read_text(encoding="utf-8"))
    return lift_graph_spec(spec)


def test_think_main_respond_routes_to_reflect_main(outer_plan) -> None:
    """Invariant C1 & ADR-0244: think.main respond must close the loop into reflect.main."""
    outgoing = tuple(e for e in outer_plan.edges if e.source == "think.main")
    assert outgoing, "outer plan must declare think.main edges"

    reg = PortRegistry()
    reg.merge_output(
        {
            "decision": Decision(
                decision_id="dec-123",
                action_type="respond",
                response_text="你好，请问有什么可以帮助您？",
                rationale="answering user",
                confidence=1.0,
            ),
            "routing": RoutingDecision(action_type=ActionType.RESPOND, should_terminate=False),
        }
    )

    chosen = select_edge(
        edges=outgoing,
        current_id="think.main",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is not None, "select_edge must pick an outgoing edge from think.main"
    assert chosen.target == "reflect.main", (
        f"ADR-0244 violation: think.main respond must route to reflect.main, got {chosen.target}"
    )


def test_act_main_should_terminate_routes_to_reflect_main(outer_plan) -> None:
    """Invariant C1 & ADR-0244: act.main completion must route to reflect.main."""
    outgoing = tuple(e for e in outer_plan.edges if e.source == "act.main")
    assert outgoing, "outer plan must declare act.main edges"

    reg = PortRegistry()
    reg.merge_output(
        {
            "decision": Decision(
                decision_id="dec-act-done",
                action_type="use_tool",
                rationale="done",
                confidence=1.0,
            ),
            "approval_routing": RoutingDecision(
                action_type=ActionType.USE_TOOL, next_hint="approve_skipped"
            ),
            "should_terminate": True,
        }
    )

    chosen = select_edge(
        edges=outgoing,
        current_id="act.main",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is not None, "select_edge must pick an outgoing edge from act.main"
    assert chosen.target == "reflect.main", (
        f"ADR-0244 violation: act.main should_terminate must route to reflect.main, got {chosen.target}"
    )


def test_reflect_main_default_routes_to_remember_main(outer_plan) -> None:
    """reflect.main without recovery hint must route to remember.main."""
    outgoing = tuple(e for e in outer_plan.edges if e.source == "reflect.main")
    assert outgoing, "outer plan must declare reflect.main edges"

    reg = PortRegistry()
    reg.merge_output(
        {
            "routing": RoutingDecision(action_type=ActionType.RESPOND, next_hint=None),
        }
    )

    chosen = select_edge(
        edges=outgoing,
        current_id="reflect.main",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is not None
    assert chosen.target == "remember.main"


def test_remember_main_routes_to_terminal_commit(outer_plan) -> None:
    """remember.main must route to terminal.commit to close the outer loop."""
    outgoing = tuple(e for e in outer_plan.edges if e.source == "remember.main")
    assert outgoing, "outer plan must declare remember.main edges"

    reg = PortRegistry()
    chosen = select_edge(
        edges=outgoing,
        current_id="remember.main",
        reader_factory=lambda src: PortReader(source_node=src, registry=reg),
    )
    assert chosen is not None
    assert chosen.target == "terminal.commit"
