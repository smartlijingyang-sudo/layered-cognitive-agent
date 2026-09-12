"""Regression guard for the v2 graph predicate + select_edge seam.

The v2 traversal's `select_edge` reads the bundle YAML edge `when:`
predicates through `lca.harness.graph.predicate.evaluate_restricted_predicate`.
A stale import in that module previously caused
`_resolve_default_predicate` to silently fall back to the literal-only
default, which returned None for every outer-plan edge and made the
traversal terminate after `perceive.main`. This test drives the real
predicate evaluator AND `select_edge` against the actual
`bundles/phase_main_outer.yaml` plan with a representative `_ResultView`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.framework.graph.interpreter import _ResultView
from lca.framework.graph.lifter import lift_graph_spec
from lca.framework.graph.traversal import (
    _PREDICATE_EVALUATOR,
    select_edge,
)
from lca.harness.graph.predicate import evaluate_restricted_predicate


@pytest.fixture(scope="module")
def outer_plan():
    spec = yaml.safe_load(
        Path("bundles/phase_main_outer.yaml").read_text(encoding="utf-8")
    )
    return lift_graph_spec(spec)


def test_predicate_module_uses_full_evaluator() -> None:
    """The bound evaluator must be the real DSL evaluator, not the
    literal-only default that misroutes every edge."""
    assert _PREDICATE_EVALUATOR is evaluate_restricted_predicate


def test_predicate_handles_python_true_literal() -> None:
    """YAML loads `when: true` / `when: True` as Python booleans; both
    must evaluate to True regardless of capitalization."""
    assert evaluate_restricted_predicate("true", result=None, artifacts={}) is True
    assert evaluate_restricted_predicate("True", result=None, artifacts={}) is True


def test_predicate_perceive_stop_guard_is_false_on_success() -> None:
    """The `perceive → stop (error)` branch must NOT fire on a
    successful perceive output (should_stop stays unset)."""
    result = _ResultView(
        type("Out", (), {"port_values": {"manifest": "ok"}, "result_kind": "", "next_hints": {}})()
    )
    assert (
        evaluate_restricted_predicate(
            'result.payload.should_stop == true and result.payload.reason == "error"',
            result=result,
            artifacts={},
        )
        is False
    )


def test_predicate_perceive_think_guard_is_true() -> None:
    """The `perceive → think` branch must fire unconditionally."""
    result = _ResultView(
        type("Out", (), {"port_values": {"manifest": "ok"}, "result_kind": "", "next_hints": {}})()
    )
    assert evaluate_restricted_predicate("True", result=result, artifacts={}) is True


def test_select_edge_picks_think_after_successful_perceive(outer_plan) -> None:
    """After a successful perceive visit, the traversal must advance to
    `think.main` rather than terminating."""
    outgoing = [e for e in outer_plan.edges if e.source == "perceive.main"]
    assert outgoing, "outer plan must declare perceive.main edges"
    result = _ResultView(
        type("Out", (), {"port_values": {"manifest": "ok"}, "result_kind": "", "next_hints": {}})()
    )
    chosen = select_edge(
        edges=tuple(outgoing),
        current_id="perceive.main",
        result=result,
        artifacts={},
    )
    assert chosen is not None, (
        "select_edge must pick the next phase after perceive; "
        "returning None means the traversal terminates after one visit"
    )
    assert chosen.target == "think.main"


def test_select_edge_picks_think_after_successful_perceive_via_port_values(outer_plan) -> None:
    """Same invariant as above, but with payload-shaped port_values — the
    shape the v2 driver actually puts on `_output.port_values` after a
    perceive subgraph returns."""
    result = _ResultView(
        type("Out", (), {"port_values": {"perceive_payload": {"manifest": "ok"}}, "result_kind": "", "next_hints": {}})()
    )
    chosen = select_edge(
        edges=tuple(e for e in outer_plan.edges if e.source == "perceive.main"),
        current_id="perceive.main",
        result=result,
        artifacts={},
    )
    assert chosen is not None
    assert chosen.target == "think.main"
