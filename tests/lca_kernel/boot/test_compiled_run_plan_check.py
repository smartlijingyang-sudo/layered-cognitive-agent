"""Tests for :func:`check_compiled_run_plan`.

Six cases cover the design:

- multi-node plan with a reserved terminal port → pass
- 1-node plan → reject (K2 expects multi-node)
- terminal node carries ``subgraph_ref`` → reject
- entry node carries ``subgraph_ref`` → reject
- terminal node emits the reserved ``terminal_outcome`` → pass
- terminal node emits a non-standard ``terminal_*`` port → reject

Construction note
-----------------

The function returns ``list[PlanLiftError]`` — a free-function shape
deliberately chosen so multiple independent failures surface in a
single boot pass (see ``compiled_run_plan.py``'s module docstring).
Per-case helpers mirror the style used by the other ``checks/``
tests in this package so the assertion patterns stay uniform.
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import (
    Plan,
    PlanEdge,
    PlanNode,
    SubgraphReference,
)
from lca_kernel.boot.plan_validation.checks.compiled_run_plan import (
    check_compiled_run_plan,
)


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


def _node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
    io_schema: NodeIOSchema | None = None,
    subgraph_ref: SubgraphReference | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=(
            BindingKind.SUBGRAPH if subgraph_ref is not None
            else BindingKind.NODE_EXECUTOR
        ),
        config={},
        terminal=terminal,
        entry=entry,
        subgraph_ref=subgraph_ref,
        io_schema=io_schema if io_schema is not None else NodeIOSchema(),
    )


def _plan(*nodes: PlanNode, edges: tuple[PlanEdge, ...] = ()) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


class TestCheckCompiledRunPlan:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.plan_id = "test.plan"

    # ------------------------------------------------------------------
    # Case 1: multi-node plan with valid terminal → pass
    # ------------------------------------------------------------------

    def test_multi_node_plan_with_valid_terminal_does_not_raise(self) -> None:
        """a → b (terminal with terminal_outcome) compiles cleanly."""
        terminal_schema = NodeIOSchema(
            outputs=(PortSpec(name="terminal_outcome"),)
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True, io_schema=terminal_schema),
            edges=(PlanEdge(source="a", target="b"),),
        )
        assert check_compiled_run_plan(plan, plan_id=self.plan_id) == []

    # ------------------------------------------------------------------
    # Case 2: 1-node plan → reject
    # ------------------------------------------------------------------

    def test_single_node_plan_raises(self) -> None:
        """A single-node plan has nothing to compile."""
        plan = _plan(
            _node("only", entry=True, terminal=True),
        )
        errors = check_compiled_run_plan(plan, plan_id=self.plan_id)
        assert len(errors) == 1
        err = errors[0]
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == self.plan_id
        assert "only 1 node" in str(err)
        assert "K2 compile_run_plan expects multi-node plans" in str(err)

    # ------------------------------------------------------------------
    # Case 3: terminal node has subgraph_ref → reject
    # ------------------------------------------------------------------

    def test_terminal_node_with_subgraph_ref_raises(self) -> None:
        """A terminal delegate would never re-enter the caller."""
        plan = _plan(
            _node("a", entry=True),
            _node(
                "b",
                terminal=True,
                subgraph_ref=_subgraph_ref(),
            ),
            edges=(PlanEdge(source="a", target="b"),),
        )
        errors = check_compiled_run_plan(plan, plan_id=self.plan_id)
        assert len(errors) == 1
        err = errors[0]
        assert err.node_id == "b"
        assert "subgraph delegate" in str(err)
        assert "terminal" in str(err)

    # ------------------------------------------------------------------
    # Case 4: entry node has subgraph_ref → reject
    # ------------------------------------------------------------------

    def test_entry_node_with_subgraph_ref_does_not_raise(self) -> None:
        """Entry delegates are a production convention (phase entry
        is typically a subgraph delegate pointing at the phase
        bundle) and must not fail-loud. Only terminal-as-delegate
        is structurally broken."""
        plan = _plan(
            _node(
                "a",
                entry=True,
                subgraph_ref=_subgraph_ref(),
            ),
            _node("b", terminal=True),
            edges=(PlanEdge(source="a", target="b"),),
        )
        errors = check_compiled_run_plan(plan, plan_id=self.plan_id)
        assert errors == []

    # ------------------------------------------------------------------
    # Case 5: terminal node outputs terminal_outcome → pass (reserved OK)
    # ------------------------------------------------------------------

    def test_terminal_node_with_reserved_port_does_not_raise(self) -> None:
        """``terminal_outcome`` is a K2 projection point — accepted."""
        terminal_schema = NodeIOSchema(
            outputs=(
                PortSpec(name="terminal_outcome"),
                PortSpec(name="diagnostic"),
            ),
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True, io_schema=terminal_schema),
            edges=(PlanEdge(source="a", target="b"),),
        )
        assert check_compiled_run_plan(plan, plan_id=self.plan_id) == []

    # ------------------------------------------------------------------
    # Case 6: terminal node outputs a non-standard terminal_* port → reject
    # ------------------------------------------------------------------

    def test_terminal_node_with_non_standard_terminal_port_raises(self) -> None:
        """``terminal_weird`` is not in the whitelist — rejected."""
        terminal_schema = NodeIOSchema(
            outputs=(PortSpec(name="terminal_weird"),),
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True, io_schema=terminal_schema),
            edges=(PlanEdge(source="a", target="b"),),
        )
        errors = check_compiled_run_plan(plan, plan_id=self.plan_id)
        assert len(errors) == 1
        err = errors[0]
        assert err.node_id == "b"
        assert err.port_name == "terminal_weird"
        assert "reserved port" in str(err)
        assert "non-standard" in str(err)
