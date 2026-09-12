"""Regression test for ADR-0219 §4 cross-subgraph results_by_phase propagation.

The outer :class:`PlanInterpreter` accumulates ``results_by_phase`` as each
phase_executor visit writes its :class:`PhaseResult` into
``node_config["results_by_phase"]`` (which is the same dict object as
``PlanInterpreter.results_by_phase``). When a subgraph node runs, the
recursive runner in :mod:`lca.framework.graph.adapter` creates a fresh
inner :class:`PlanInterpreter` whose own ``results_by_phase={}`` is
independent of the outer's mirror. The inner phases therefore write to
a dict the outer never sees, and downstream phases
(``reflect.main`` / ``remember.main`` / ``stop.main``) read ``None`` for
prior phase payloads. The agent then runs ``perceive.main`` to
``max_visits=8`` and crashes.

The seam that closes the gap is :meth:`SubgraphStrategy.execute`. It
must hand the outer mirror (read from ``context.node_config``) into the
recursive runner as a new parameter. The recursive runner must hand it
into the inner :class:`PlanInterpreter` so mutations on the inner side
flow back to the outer.

These tests pin the contract at the strategy boundary:

- ``SubgraphStrategy.execute`` must pass the outer mirror into the
  recursive runner as a keyword argument.
- The recursive runner must pass the shared mirror into the inner
  :class:`PlanInterpreter`, so the inner sees entries the outer
  accumulates and the outer sees entries the inner accumulates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseResult,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput
from lca.contracts.protocols.graph.plan import (
    Plan,
    SubgraphReference,
)
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.strategies import SubgraphStrategy


def _phase_result(result_kind: str) -> PhaseResult:
    return PhaseResult(result_kind=result_kind, payload=None)


class TestSubgraphStrategyForwardsOuterMirror:
    async def test_strategy_passes_outer_mirror_into_recursive_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        async def _runner(sub_plan, outer_state, depth, port_registry=None, outer_mirror=None):
            captured["outer_mirror"] = outer_mirror
            return {}

        from lca.framework.graph.strategies import subgraph_strategy as sg_mod

        monkeypatch.setattr(
            sg_mod,
            "_load_subgraph_plan",
            lambda plan_ref, entry_node: Plan(id="inner", nodes=(), edges=(), declared_inputs=()),
        )
        strategy = SubgraphStrategy(recursive_runner=_runner, max_depth=4)
        outer_mirror: dict[SemanticPhase, PhaseResult] = {
            SemanticPhase.THINK: _phase_result("decision")
        }
        ctx = StrategyContext(
            plan_ref="outer.yaml",
            node_id="think.main",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={"results_by_phase": outer_mirror},
            subgraph_ref=SubgraphReference(plan_ref="inner.yaml", entry_node="a", binding_edge="x"),
        )
        await strategy.execute(ctx, NodeInput(port_values={}, consumer_node="think.main"))
        assert captured["outer_mirror"] is outer_mirror

    async def test_strategy_uses_empty_mirror_when_node_config_omits_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        async def _runner(sub_plan, outer_state, depth, port_registry=None, outer_mirror=None):
            captured["outer_mirror"] = outer_mirror
            return {}

        from lca.framework.graph.strategies import subgraph_strategy as sg_mod

        monkeypatch.setattr(
            sg_mod,
            "_load_subgraph_plan",
            lambda plan_ref, entry_node: Plan(id="inner", nodes=(), edges=(), declared_inputs=()),
        )
        strategy = SubgraphStrategy(recursive_runner=_runner, max_depth=4)
        ctx = StrategyContext(
            plan_ref="outer.yaml",
            node_id="think.main",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
            subgraph_ref=SubgraphReference(plan_ref="inner.yaml", entry_node="a", binding_edge="x"),
        )
        await strategy.execute(ctx, NodeInput(port_values={}, consumer_node="think.main"))
        assert captured["outer_mirror"] == {}
