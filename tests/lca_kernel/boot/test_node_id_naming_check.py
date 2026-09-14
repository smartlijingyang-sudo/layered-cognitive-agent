"""Tests for :class:`NodeIdNamingCheck`.

Seven cases cover the design:

- canonical dotted ids → pass
- single-segment lowercase ids → pass (plan-level simple plan)
- ``_payload`` suffix → reject
- ``_outcome`` suffix → reject
- PascalCase → reject (invalid format)
- kebab-case (with dash) → reject (invalid format)
- empty id is not exercised here (lifter rejects it earlier)
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca_kernel.boot.plan_validation.checks.node_id_naming import (
    NodeIdNamingCheck,
)


def _node(node_id: str, *, entry: bool = False, terminal: bool = False) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        entry=entry,
        terminal=terminal,
    )


def _plan(*node_ids: str) -> Plan:
    if not node_ids:
        return Plan(id="test.plan", nodes=())
    nodes = [_node(node_ids[0], entry=True)]
    nodes.extend(
        _node(nid, terminal=(i == len(node_ids) - 1)) for i, nid in enumerate(node_ids[1:], start=1)
    )
    return Plan(id="test.plan", nodes=tuple(nodes))


class TestNodeIdNamingCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = NodeIdNamingCheck()

    # ------------------------------------------------------------------
    # Case 1: canonical dotted ids → pass
    # ------------------------------------------------------------------

    def test_canonical_dotted_ids_pass(self) -> None:
        """``phase.<name>.<step>`` and ``concept.<name>.<step>`` pass."""
        plan = _plan("phase.perceive.observe", "concept.decision.parse")
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: single-segment lowercase → pass (plan-level simple plan)
    # ------------------------------------------------------------------

    def test_single_segment_lowercase_ids_pass(self) -> None:
        """``a`` / ``b`` are valid plan-level ids — no namespace required."""
        plan = _plan("a", "b")
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: ``_payload`` suffix → reject
    # ------------------------------------------------------------------

    def test_payload_suffix_raises(self) -> None:
        """``perceive_payload_fold`` carries ``_payload_`` mid-id → reject."""
        plan = _plan("perceive_payload_fold")
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "phase_alias_infix" in str(err)
        assert "perceive_payload_fold" in str(err)

    # ------------------------------------------------------------------
    # Case 4: ``_outcome`` suffix → reject
    # ------------------------------------------------------------------

    def test_outcome_suffix_raises(self) -> None:
        """``act_outcome_emit`` carries ``_outcome_`` mid-id → reject."""
        plan = _plan("act_outcome_emit")
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "phase_alias_infix" in str(err)
        assert "act_outcome_emit" in str(err)

    # ------------------------------------------------------------------
    # Case 5: PascalCase → reject (invalid format)
    # ------------------------------------------------------------------

    def test_pascal_case_raises(self) -> None:
        """``BadName`` starts with uppercase → reject as invalid format."""
        plan = _plan("BadName")
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "invalid_format" in str(err)
        assert "BadName" in str(err)

    # ------------------------------------------------------------------
    # Case 6: kebab-case (with dash) → reject (invalid format)
    # ------------------------------------------------------------------

    def test_kebab_case_raises(self) -> None:
        """``step-a`` contains a dash → reject as invalid format."""
        plan = _plan("step-a")
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "invalid_format" in str(err)
        assert "step-a" in str(err)

    # ------------------------------------------------------------------
    # Meta: stable check_id and label
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "node_id_naming"
        assert self.check.label
