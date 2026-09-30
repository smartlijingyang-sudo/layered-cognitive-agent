"""Focused unit tests for the split plan-validation helper modules.

The package ``lca_kernel.boot.plan_validation`` was split from a single
``__init__.py`` into focused submodules (``core``, ``reachability``,
``typed_ports``, ``bundle_mapping``, ``predicates``). These tests import
every helper through the re-exported barrel so they prove the public
surface still works unchanged after the split.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca_kernel.boot.plan_validation import (
    _apply_entry_fallback,
    _check_reachability,
    _check_string_predicate,
    _check_terminal_no_outgoing_edges,
    _check_terminal_reachable_from_entry,
    _check_typed_port_wiring,
    _select_outer_plan,
    _subgraph_ref_with_entry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
) -> PlanNode:
    """Build a :class:`PlanNode` with the given typed ports."""
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        io_schema=NodeIOSchema(
            inputs=tuple(PortSpec(name=p) for p in inputs),
            outputs=tuple(PortSpec(name=p) for p in outputs),
        ),
        entry=entry,
        terminal=terminal,
    )


def _plan(*nodes: PlanNode, edges: tuple[PlanEdge, ...] = ()) -> Plan:
    """Build a :class:`Plan` with exactly one entry node."""
    return Plan(id="test.plan", nodes=nodes, edges=edges)


def _edge(source: str, target: str) -> PlanEdge:
    return PlanEdge(source=source, target=target)


def _write_bundle(tmp_path: Path, name: str, mapping: dict[str, object]) -> str:
    """Write a YAML bundle and return its absolute path."""
    path = tmp_path / name
    path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Reachability helpers (barrel re-export)
# ---------------------------------------------------------------------------


class TestCheckReachability:
    def test_reachable_plan_passes(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_reachability(plan, plan_id="test.plan") is None

    def test_island_node_raises(self) -> None:
        plan = _plan(
            _node("a", entry=True, terminal=True, outputs=("x",)),
            _node("island", outputs=("y",)),
        )
        err = _check_reachability(plan, plan_id="test.plan")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert "island" in str(err)
        assert "unreachable" in str(err)

    def test_empty_plan_passes(self) -> None:
        plan = _plan()
        assert _check_reachability(plan, plan_id="test.plan") is None


class TestCheckTypedPortWiring:
    def test_required_input_produced_passes(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_typed_port_wiring(plan, plan_id="test.plan") is None

    def test_missing_input_raises(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("foo",)),
            _node("b", terminal=True, inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        err = _check_typed_port_wiring(plan, plan_id="test.plan")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert "x" in str(err)
        assert "not produced" in str(err)

    def test_entry_inputs_out_of_scope(self) -> None:
        # Entry inputs are supplied by the outer caller, so a missing
        # predecessor for an entry input is not a wiring fault.
        plan = _plan(
            _node("a", entry=True, inputs=("x",), outputs=("y",)),
            _node("b", terminal=True, inputs=("y",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_typed_port_wiring(plan, plan_id="test.plan") is None

    def test_self_declared_output_satisfies_input(self) -> None:
        # A node starts with its own declared outputs in the available
        # set, so a self-produced port satisfies its own requirement.
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",), outputs=("x",)),
        )
        assert _check_typed_port_wiring(plan, plan_id="test.plan") is None


class TestCheckTerminalReachableFromEntry:
    def test_terminal_reachable_passes(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_terminal_reachable_from_entry(plan, plan_id="test.plan") is None

    def test_terminal_unreachable_raises(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
        )
        err = _check_terminal_reachable_from_entry(plan, plan_id="test.plan")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert "terminal" in str(err)
        assert "unreachable" in str(err)

    def test_no_terminal_skipped(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_terminal_reachable_from_entry(plan, plan_id="test.plan") is None


class TestCheckTerminalNoOutgoingEdges:
    def test_terminal_sink_passes(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
            edges=(_edge("a", "b"),),
        )
        assert _check_terminal_no_outgoing_edges(plan, plan_id="test.plan") is None

    def test_terminal_with_outgoing_edge_raises(self) -> None:
        plan = _plan(
            _node("a", entry=True, outputs=("x",)),
            _node("b", terminal=True, inputs=("x",)),
            _node("c", inputs=("y",)),
            edges=(_edge("a", "b"), _edge("b", "c")),
        )
        err = _check_terminal_no_outgoing_edges(plan, plan_id="test.plan")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert "terminal" in str(err)
        assert "outgoing" in str(err)


# ---------------------------------------------------------------------------
# Predicate helper (barrel re-export)
# ---------------------------------------------------------------------------


class TestCheckStringPredicate:
    def test_string_predicate_rejected(self) -> None:
        spec = {
            "id": "broken",
            "edges": [{"from": "a", "to": "b", "when": 'result.payload.x == "y"'}],
        }
        err = _check_string_predicate(spec, plan_id="broken")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert "string when" in str(err)

    @pytest.mark.parametrize("alias", ["true", "false", ""])
    def test_legacy_aliases_allowed(self, alias: str) -> None:
        spec = {"id": "ok", "edges": [{"from": "a", "to": "b", "when": alias}]}
        assert _check_string_predicate(spec, plan_id="ok") is None

    def test_typed_predicate_allowed(self) -> None:
        spec = {
            "id": "ok",
            "edges": [
                {"from": "a", "to": "b", "when": {"kind": "eq", "port": {"name": "x"}, "value": 1}},
            ],
        }
        assert _check_string_predicate(spec, plan_id="ok") is None


# ---------------------------------------------------------------------------
# Bundle-mapping helpers (barrel re-export)
# ---------------------------------------------------------------------------


class TestApplyEntryFallback:
    def test_injects_entry_on_first_node(self) -> None:
        spec = {
            "id": "legacy",
            "nodes": [{"id": "a", "binding": "node_executor"}],
        }
        result = _apply_entry_fallback(spec)
        assert result["nodes"][0]["entry"] is True

    def test_preserves_existing_entry(self) -> None:
        spec = {
            "id": "modern",
            "nodes": [
                {"id": "a", "binding": "node_executor", "entry": True},
                {"id": "b", "binding": "node_executor"},
            ],
        }
        result = _apply_entry_fallback(spec)
        assert result["nodes"][0]["entry"] is True

    def test_returns_copy(self) -> None:
        spec = {"id": "x", "nodes": [{"id": "a", "binding": "node_executor"}]}
        result = _apply_entry_fallback(spec)
        assert result is not spec
        assert spec["nodes"][0].get("entry") is None


class TestSelectOuterPlan:
    def test_skips_subgraph_bundles(self, tmp_path: Path) -> None:
        sub_path = _write_bundle(
            tmp_path,
            "think.subgraph.yaml",
            {"id": "think.subgraph", "nodes": [{"id": "a", "binding": "node_executor"}]},
        )
        outer_path = _write_bundle(
            tmp_path,
            "phase_main_outer.yaml",
            {"id": "outer", "nodes": [{"id": "a", "binding": "node_executor"}]},
        )
        mapping, path = _select_outer_plan((sub_path, outer_path), profile_dir=tmp_path)
        assert mapping is not None
        assert mapping["id"] == "outer"
        assert path == Path(outer_path)

    def test_no_plan_shaped_bundle(self, tmp_path: Path) -> None:
        not_a_plan = _write_bundle(tmp_path, "not_a_plan.yaml", {"id": "x"})
        mapping, path = _select_outer_plan((not_a_plan,), profile_dir=tmp_path)
        assert mapping is None
        assert path is None


class TestSubgraphRefWithEntry:
    def test_discovers_inner_plan_with_entry(self, tmp_path: Path) -> None:
        inner_path = _write_bundle(
            tmp_path,
            "inner.yaml",
            {
                "id": "inner",
                "nodes": [{"id": "only", "binding": "node_executor"}],
            },
        )
        outer = {
            "id": "outer",
            "nodes": [
                {
                    "id": "a",
                    "binding": "node_executor",
                    "entry": True,
                    "sub_spec_ref": {
                        "plan_ref": Path(inner_path).name,
                        "entry_node": "only",
                    },
                }
            ],
        }
        inner_mappings = _subgraph_ref_with_entry(
            outer,
            path_resolver=lambda ref: tmp_path / ref,
        )
        assert len(inner_mappings) == 1
        inner_mapping, inner_id = inner_mappings[0]
        assert inner_id == "inner"
        assert inner_mapping["entry"] == "only"

    def test_recurse_into_chained_subgraph(self, tmp_path: Path) -> None:
        leaf_path = _write_bundle(
            tmp_path,
            "leaf.yaml",
            {
                "id": "leaf",
                "nodes": [{"id": "leaf_only", "binding": "node_executor"}],
            },
        )
        mid_path = _write_bundle(
            tmp_path,
            "mid.yaml",
            {
                "id": "mid",
                "nodes": [
                    {
                        "id": "mid_only",
                        "binding": "node_executor",
                        "sub_spec_ref": {
                            "plan_ref": Path(leaf_path).name,
                            "entry_node": "leaf_only",
                        },
                    }
                ],
            },
        )
        outer = {
            "id": "outer",
            "nodes": [
                {
                    "id": "a",
                    "binding": "node_executor",
                    "entry": True,
                    "sub_spec_ref": {
                        "plan_ref": Path(mid_path).name,
                        "entry_node": "mid_only",
                    },
                }
            ],
        }
        inner_mappings = _subgraph_ref_with_entry(
            outer,
            recurse=True,
            path_resolver=lambda ref: tmp_path / ref,
        )
        ids = {inner_id for _mapping, inner_id in inner_mappings}
        assert ids == {"mid", "leaf"}
