"""Tests for :class:`UnusedPortsCheck`.

Seven cases cover the decision tree:

- a→b with ``a.outputs=[x]`` and ``b.inputs=[x]`` → pass
- entry→a→b with ``a.outputs=[x, y]`` and ``b.inputs=[x]`` (y unused) → fail
- entry→a→b→c with ``b.outputs=[x]`` and ``c`` not reading x → fail
- entry→a→b where ``b`` is terminal (terminal skips its own outputs) → pass
- entry→a→terminal with ``a.outputs=[x]`` (terminal doesn't read x) → fail
- subgraph delegate node with arbitrary outputs → pass (skip)
- linear a→b→c with all ports consumed → pass
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
from lca_kernel.boot.plan_validation.checks.unused_ports import UnusedPortsCheck


def _node(
    node_id: str,
    *,
    schema: NodeIOSchema | None = None,
    entry: bool = False,
    terminal: bool = False,
    subgraph_ref: SubgraphReference | None = None,
) -> PlanNode:
    binding = BindingKind.SUBGRAPH if subgraph_ref is not None else BindingKind.NODE_EXECUTOR
    return PlanNode(
        id=node_id,
        binding=binding,
        io_schema=schema or NodeIOSchema(),
        entry=entry,
        terminal=terminal,
        subgraph_ref=subgraph_ref,
    )


def _plan(
    *nodes: PlanNode,
    edges: tuple[PlanEdge, ...] = (),
) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


def _edge(source: str, target: str) -> PlanEdge:
    return PlanEdge(source=source, target=target)


def _schema(
    *,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
) -> NodeIOSchema:
    return NodeIOSchema(
        inputs=tuple(PortSpec(name=n, required=True) for n in inputs),
        outputs=tuple(PortSpec(name=n) for n in outputs),
    )


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


class TestUnusedPortsCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = UnusedPortsCheck()

    # ------------------------------------------------------------------
    # Case 1: a→b, a.outputs=[x], b.inputs=[x] → pass
    # ------------------------------------------------------------------

    def test_outputs_consumed_does_not_raise(self) -> None:
        plan = _plan(
            _node("entry", entry=True),
            _node("a", schema=_schema(outputs=("x",))),
            _node("b", schema=_schema(inputs=("x",)), terminal=True),
            edges=(_edge("entry", "a"), _edge("a", "b")),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: a→b with a.outputs=[x, y] and b.inputs=[x] → fail
    #         (a is non-entry so the check fires on it)
    # ------------------------------------------------------------------

    def test_dead_output_raises(self) -> None:
        plan = _plan(
            _node("entry", entry=True),
            _node("a", schema=_schema(outputs=("x", "y"))),
            _node("b", schema=_schema(inputs=("x",)), terminal=True),
            edges=(_edge("entry", "a"), _edge("a", "b")),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "a"
        assert err.port_name == "y"
        msg = str(err)
        assert "'y'" in msg
        assert "dead output" in msg

    # ------------------------------------------------------------------
    # Case 3: a→b→c with b producing x that nobody reads → fail
    # ------------------------------------------------------------------

    def test_middle_node_with_unconsumed_output_raises(self) -> None:
        """a has no outputs; b has output ``x`` but c does not
        require ``x`` → dead output on b."""
        plan = _plan(
            _node("entry", entry=True),
            _node("a"),
            _node("b", schema=_schema(outputs=("x",))),
            _node("c", terminal=True),
            edges=(
                _edge("entry", "a"),
                _edge("a", "b"),
                _edge("b", "c"),
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.node_id == "b"
        assert err.port_name == "x"

    # ------------------------------------------------------------------
    # Case 4: terminal b with outputs that aren't required — terminal
    # skips its own check, predecessor has no outputs → pass.
    # ------------------------------------------------------------------

    def test_terminal_node_skipped_does_not_raise(self) -> None:
        """Predecessor a has no outputs; b is terminal with
        arbitrary outputs. The check fires on a (no outputs → no
        finding) and skips b. Pass."""
        plan = _plan(
            _node("entry", entry=True),
            _node("a"),
            _node("b", schema=_schema(outputs=("x",)), terminal=True),
            edges=(_edge("entry", "a"), _edge("a", "b")),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 5: a→terminal where a (non-entry) has outputs the terminal
    # does not require → fail.
    # ------------------------------------------------------------------

    def test_predecessor_with_unconsumed_output_raises(self) -> None:
        """a is non-entry, produces ``x``; b is terminal and does not
        declare ``x`` as a required input → dead output on a."""
        plan = _plan(
            _node("entry", entry=True),
            _node("a", schema=_schema(outputs=("x",))),
            _node("b", terminal=True),
            edges=(_edge("entry", "a"), _edge("a", "b")),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.node_id == "a"
        assert err.port_name == "x"

    # ------------------------------------------------------------------
    # Case 6: entry node is skipped from the check (its outputs are
    # consumed by the outer caller, not by an in-plan successor).
    # ------------------------------------------------------------------

    def test_entry_node_outputs_are_skipped(self) -> None:
        """Entry node alone with an output → out of scope; no raise."""
        plan = _plan(
            _node("only", schema=_schema(outputs=("x",)), entry=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 7: subgraph delegate node is skipped from the check.
    # ------------------------------------------------------------------

    def test_subgraph_delegate_with_outputs_is_skipped(self) -> None:
        plan = _plan(
            _node("entry", entry=True),
            _node(
                "sg",
                schema=_schema(outputs=("decision",)),
                subgraph_ref=_subgraph_ref(),
            ),
            _node("downstream", terminal=True),
            edges=(
                _edge("entry", "sg"),
                _edge("sg", "downstream"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    def test_subgraph_delegate_with_unrelated_outputs_is_skipped(self) -> None:
        plan = _plan(
            _node("entry", entry=True),
            _node(
                "sg",
                schema=_schema(outputs=("decision", "leftover")),
                subgraph_ref=_subgraph_ref(),
            ),
            _node("downstream", terminal=True),
            edges=(
                _edge("entry", "sg"),
                _edge("sg", "downstream"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 8: linear a→b→c with all ports consumed → pass
    # ------------------------------------------------------------------

    def test_linear_chain_all_consumed_does_not_raise(self) -> None:
        plan = _plan(
            _node("entry", entry=True),
            _node("a", schema=_schema(outputs=("x",))),
            _node("b", schema=_schema(inputs=("x",), outputs=("y",))),
            _node("c", schema=_schema(inputs=("y",)), terminal=True),
            edges=(
                _edge("entry", "a"),
                _edge("a", "b"),
                _edge("b", "c"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Bonus: a node with no outputs at all is never flagged.
    # ------------------------------------------------------------------

    def test_node_with_no_outputs_does_not_raise(self) -> None:
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge("a", "b"),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # check_id / label are stable.
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "unused_ports"
        assert self.check.label
