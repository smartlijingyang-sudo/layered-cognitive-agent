"""Tests for :class:`PlanIdAliasSuffixCheck`.

Every resource-alias plan id must be rejected at boot; canonical
``phase.<name>`` ids must pass cleanly.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from lca_kernel.boot.plan_validation.checks.phase_boundary_ssot import (
    PlanIdAliasSuffixCheck,
)


def _plan(plan_id: str) -> Plan:
    """Minimal plan with no nodes — this check only inspects *plan_id*."""
    return Plan(id=plan_id, nodes=(), edges=())


class TestPlanIdAliasSuffixCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = PlanIdAliasSuffixCheck()

    # ------------------------------------------------------------------
    # Failure cases — phase-alias suffixes
    # ------------------------------------------------------------------

    def test_perceive_payload_subgraph_raises(self) -> None:
        """``perceive_payload_subgraph`` ends in ``_payload`` → reject."""
        err = self.check.run(
            _plan("perceive_payload_subgraph"),
            plan_id="perceive_payload_subgraph",
        )
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "perceive_payload_subgraph"
        assert "_payload" in str(err)

    def test_act_outcome_subgraph_raises(self) -> None:
        """``act_outcome_subgraph`` ends in ``_outcome`` → reject."""
        err = self.check.run(
            _plan("act_outcome_subgraph"),
            plan_id="act_outcome_subgraph",
        )
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "act_outcome_subgraph"
        assert "_outcome" in str(err)

    def test_perceive_payload_inner_raises(self) -> None:
        """``perceive_payload_inner`` has ``_payload_`` mid-id → reject."""
        err = self.check.run(
            _plan("perceive_payload_inner"),
            plan_id="perceive_payload_inner",
        )
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "perceive_payload_inner"
        assert "_payload_" in str(err)

    # ------------------------------------------------------------------
    # Passing cases — canonical naming
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "plan_id",
        [
            "phase.perceive",
            "phase.main.outer",
            "concept.decision.enforce",
            "think.subgraph",
        ],
    )
    def test_canonical_ids_pass(self, plan_id: str) -> None:
        """Canonical ``phase.<name>`` / domain ids must not raise."""
        result = self.check.run(_plan(plan_id), plan_id=plan_id)
        assert result is None
