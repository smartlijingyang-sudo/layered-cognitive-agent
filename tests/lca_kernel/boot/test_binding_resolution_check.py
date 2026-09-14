"""Tests for :class:`BindingResolutionCheck`.

Six cases cover the decision tree:

- NODE_EXECUTOR + well-formed factory → pass
- NODE_EXECUTOR + empty factory → reject
- NODE_EXECUTOR + factory with whitespace → reject
- TERMINATE binding (no factory needed) → pass
- SUBGRAPH binding (no factory needed) → pass
- NODE_EXECUTOR + factory with capital letter / wrong shape → reject

Plus structural assertions for ``check_id`` / ``label``.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanNode, SubgraphReference

from lca_kernel.boot.plan_validation.checks.binding_resolution import (
    BindingResolutionCheck,
)


def _executor_node(
    node_id: str,
    factory: str,
    *,
    entry: bool = False,
    terminal: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        config={"factory": factory},
        entry=entry,
        terminal=terminal,
    )


def _terminate_node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.TERMINATE,
        config={},
        entry=entry,
        terminal=terminal,
    )


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


def _subgraph_node(
    node_id: str,
    *,
    entry: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.SUBGRAPH,
        subgraph_ref=_subgraph_ref(),
        config={},
        entry=entry,
    )


def _plan(*nodes: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes))


class TestBindingResolutionCheck:
    def setup_method(self) -> None:
        self.check = BindingResolutionCheck()

    # ------------------------------------------------------------------
    # Case 1: NODE_EXECUTOR + valid factory → pass
    # ------------------------------------------------------------------

    def test_valid_factory_does_not_raise(self) -> None:
        """`phase.perceive.observe` is a well-formed 3-segment dotted factory."""
        plan = _plan(
            _executor_node("a", "phase.perceive.observe", entry=True),
            _terminate_node("b", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: NODE_EXECUTOR + empty factory → reject
    # ------------------------------------------------------------------

    def test_empty_factory_raises(self) -> None:
        """Empty factory string fails the non-empty check."""
        plan = _plan(
            _executor_node("a", "", entry=True),
            _terminate_node("b", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "a"
        assert "factory" in str(err)

    # ------------------------------------------------------------------
    # Case 3: NODE_EXECUTOR + factory with spaces → reject
    # ------------------------------------------------------------------

    def test_factory_with_spaces_raises(self) -> None:
        """Whitespace in the factory string fails the regex."""
        plan = _plan(
            _executor_node("a", "bad name with spaces", entry=True),
            _terminate_node("b", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.node_id == "a"
        assert "malformed" in str(err)

    # ------------------------------------------------------------------
    # Case 4: TERMINATE binding → pass (factory not required)
    # ------------------------------------------------------------------

    def test_terminate_binding_does_not_raise(self) -> None:
        """TERMINATE is a built-in leaf; no factory string needed."""
        plan = _plan(
            _executor_node("a", "phase.perceive.observe", entry=True),
            _terminate_node("b", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 5: SUBGRAPH binding → pass (factory not required)
    # ------------------------------------------------------------------

    def test_subgraph_binding_does_not_raise(self) -> None:
        """SUBGRAPH delegates dispatch via subgraph_ref, not factory."""
        plan = _plan(
            _subgraph_node("sg", entry=True),
            _terminate_node("b", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 6: NODE_EXECUTOR + factory with capital letter → reject
    # ------------------------------------------------------------------

    def test_factory_with_capital_letter_raises(self) -> None:
        """`uppercase.StartsWrong` fails the lowercase regex."""
        plan = _plan(
            _executor_node("a", "uppercase.StartsWrong", entry=True),
            _terminate_node("b", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.node_id == "a"
        assert "malformed" in str(err)

    # ------------------------------------------------------------------
    # Structural assertions
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "binding_resolution"
        assert self.check.label