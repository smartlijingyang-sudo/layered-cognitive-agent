"""Tests for :class:`NodeEventEmissionCheck`.

Nine cases cover the decision tree:

- entry node with non-empty ``emit_on_enter`` → pass
- entry node with empty ``emit_on_enter`` → reject
- entry node missing ``emit_on_enter`` key entirely → reject
- terminal node with non-empty ``emit_on_exit`` → pass
- terminal node with empty ``emit_on_exit`` → reject
- plain node with both emits declared → pass
- plain node with empty config → pass (leaf default)
- malformed ``emit_on_enter`` (string instead of list) → reject
- subgraph delegate node with no emits → pass (subgraph owns)

Plus structural assertions for ``check_id`` / ``label``.

Construction note
-----------------

``Plan`` carries an ``@model_validator`` that rejects 0 or >1
entries at construction time. The malformed ``emit_on_enter``
case (case 8) builds a single-node plan where that node is both
entry and terminal, which keeps the validator happy while still
exercising the malformed-shape path.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanNode, SubgraphReference
from lca_kernel.boot.plan_validation.checks.node_event_emission import (
    NodeEventEmissionCheck,
)


def _executor_node(
    node_id: str,
    *,
    config: dict[str, object] | None = None,
    entry: bool = False,
    terminal: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        config=config if config is not None else {},
        entry=entry,
        terminal=terminal,
    )


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


def _subgraph_node(node_id: str, *, entry: bool = False) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.SUBGRAPH,
        subgraph_ref=_subgraph_ref(),
        config={},
        entry=entry,
    )


def _plan(*nodes: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes))


class TestNodeEventEmissionCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = NodeEventEmissionCheck()

    # ------------------------------------------------------------------
    # Case 1: entry node with non-empty emit_on_enter → pass
    # ------------------------------------------------------------------

    def test_entry_with_emit_on_enter_does_not_raise(self) -> None:
        """Entry declares ``[plan.start]`` → journal has a start anchor."""
        plan = _plan(
            _executor_node(
                "a",
                config={"emit_on_enter": ["plan.start"]},
                entry=True,
            ),
            _executor_node(
                "b",
                config={"emit_on_exit": ["plan.end"]},
                terminal=True,
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: entry node with empty emit_on_enter → reject
    # ------------------------------------------------------------------

    def test_entry_with_empty_emit_on_enter_raises(self) -> None:
        """Entry declares ``[]`` → no anchor, trace has no start frame."""
        plan = _plan(
            _executor_node("a", config={"emit_on_enter": []}, entry=True),
            _executor_node("b", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "a"
        assert "entry needs emit_on_enter" in str(err)

    # ------------------------------------------------------------------
    # Case 3: entry node missing emit_on_enter entirely → reject
    # ------------------------------------------------------------------

    def test_entry_missing_emit_on_enter_raises(self) -> None:
        """Entry has no ``emit_on_enter`` key at all → treated as absent."""
        plan = _plan(
            _executor_node("a", config={}, entry=True),
            _executor_node("b", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "a"
        assert "entry needs emit_on_enter" in str(err)

    # ------------------------------------------------------------------
    # Case 4: terminal node with non-empty emit_on_exit → pass
    # ------------------------------------------------------------------

    def test_terminal_with_emit_on_exit_does_not_raise(self) -> None:
        """Terminal declares ``[plan.end]`` → journal has an end anchor."""
        plan = _plan(
            _executor_node(
                "a",
                config={"emit_on_enter": ["plan.start"]},
                entry=True,
            ),
            _executor_node(
                "b",
                config={"emit_on_exit": ["plan.end"]},
                terminal=True,
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 5: terminal node with empty emit_on_exit → reject
    # ------------------------------------------------------------------

    def test_terminal_with_empty_emit_on_exit_raises(self) -> None:
        """Terminal declares ``[]`` → trace has no completion frame."""
        plan = _plan(
            _executor_node(
                "a",
                config={"emit_on_enter": ["plan.start"]},
                entry=True,
            ),
            _executor_node("b", config={"emit_on_exit": []}, terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "b"
        assert "terminal needs emit_on_exit" in str(err)

    # ------------------------------------------------------------------
    # Case 6: plain node with both emits declared → pass
    # ------------------------------------------------------------------

    def test_plain_node_with_both_emits_does_not_raise(self) -> None:
        """Middle node declares both → no rule violation."""
        plan = _plan(
            _executor_node(
                "a",
                config={"emit_on_enter": ["plan.start"]},
                entry=True,
            ),
            _executor_node(
                "middle",
                config={
                    "emit_on_enter": ["step.in"],
                    "emit_on_exit": ["step.out"],
                },
            ),
            _executor_node(
                "b",
                config={"emit_on_exit": ["plan.end"]},
                terminal=True,
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 7: plain node with empty config → pass (leaf default)
    # ------------------------------------------------------------------

    def test_plain_node_with_empty_config_does_not_raise(self) -> None:
        """Middle leaf has no events → fine, only entry/terminal are gated."""
        plan = _plan(
            _executor_node(
                "a",
                config={"emit_on_enter": ["plan.start"]},
                entry=True,
            ),
            _executor_node("middle", config={}),
            _executor_node(
                "b",
                config={"emit_on_exit": ["plan.end"]},
                terminal=True,
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 8: malformed emit_on_enter (string instead of list) → reject
    # ------------------------------------------------------------------

    def test_malformed_emit_on_enter_raises(self) -> None:
        """``emit_on_enter: "plan.start"`` is a string, not a list."""
        plan = _plan(
            _executor_node(
                "a",
                config={
                    "emit_on_enter": "plan.start",
                    "emit_on_exit": ["plan.end"],
                },
                entry=True,
                terminal=True,
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "a"
        assert "emit_on_enter malformed" in str(err)

    # ------------------------------------------------------------------
    # Case 9: subgraph delegate node without emits → pass
    # ------------------------------------------------------------------

    def test_subgraph_node_without_emits_does_not_raise(self) -> None:
        """Subgraph delegate owns its inner plan's observability contract."""
        plan = _plan(
            _subgraph_node("sg", entry=True),
            _executor_node(
                "b",
                config={"emit_on_exit": ["plan.end"]},
                terminal=True,
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Structural assertions
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "node_event_emission"
        assert self.check.label
