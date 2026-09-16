"""M1 compile contract: missing / unbound admit_recovery edge fails loud."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.framework.graph.lifter import lift_graph_spec
from lca_kernel.boot.plan_validation.checks.admit_recovery_edge import (
    AdmitRecoveryEdgeCheck,
)

REPO = Path(__file__).resolve().parents[3]
OUTER = REPO / "bundles" / "outer" / "phase_main.yaml"


def _load_outer() -> dict[str, Any]:
    return yaml.safe_load(OUTER.read_text(encoding="utf-8"))


def test_outer_phase_main_lifts_with_bounded_recovery_edge() -> None:
    """Production outer SSOT must lift and carry bounded admit_recovery."""
    plan = lift_graph_spec(_load_outer())
    assert plan.id == "phase.main.outer"
    err = AdmitRecoveryEdgeCheck().run(plan, plan_id=plan.id)
    assert err is None
    recovery = [
        e
        for e in plan.edges
        if e.source == "reflect.main"
        and e.target == "think.main"
        and e.when is not None
    ]
    assert len(recovery) == 1
    assert recovery[0].loop is not None
    assert recovery[0].loop.max_iterations == 1
    assert recovery[0].loop.budget == "run.steps"


def test_missing_admit_recovery_edge_fails_compile() -> None:
    """Stripping the recovery edge must fail loud — no soft skip."""
    spec = _load_outer()
    spec["edges"] = [
        e
        for e in spec["edges"]
        if not (
            e.get("from") == "reflect.main"
            and e.get("to") == "think.main"
            and isinstance(e.get("when"), dict)
        )
    ]
    plan = lift_graph_spec(spec)
    err = AdmitRecoveryEdgeCheck().run(plan, plan_id=plan.id)
    assert err is not None
    assert isinstance(err, PlanLiftError)
    assert "missing critical recovery edge" in str(err)
    assert "admit_recovery" in str(err)
    assert "no silent skip" in str(err)


def test_unbounded_admit_recovery_edge_fails_compile() -> None:
    """Recovery edge without loop obligation is a compile failure."""
    spec = deepcopy(_load_outer())
    for edge in spec["edges"]:
        if (
            edge.get("from") == "reflect.main"
            and edge.get("to") == "think.main"
            and isinstance(edge.get("when"), dict)
        ):
            edge.pop("loop", None)
            break
    plan = lift_graph_spec(spec)
    err = AdmitRecoveryEdgeCheck().run(plan, plan_id=plan.id)
    assert err is not None
    assert "missing loop obligation" in str(err)


def test_non_outer_plans_are_not_forced_to_declare_recovery() -> None:
    """Inner subgraphs / fixtures must not inherit the outer obligation."""
    plan = lift_graph_spec(
        {
            "id": "think.subgraph",
            "nodes": [
                {"id": "a", "binding": "node_executor", "entry": True, "outputs": ["x"]},
                {"id": "b", "binding": "node_executor", "terminal": True, "inputs": ["x"]},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
    )
    assert AdmitRecoveryEdgeCheck().run(plan, plan_id=plan.id) is None
