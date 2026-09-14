"""Tests for :class:`PortNamingConventionCheck`.

Six cases cover the canonical names that pass and the four
failure modes (alias suffix, PascalCase, kebab-case, whitespace)
that the check rejects at boot.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanNode

from lca_kernel.boot.plan_validation.checks.port_naming import (
    PortNamingConventionCheck,
)


def _node(node_id: str, ports: tuple[PortSpec, ...], *, outputs: bool = False) -> PlanNode:
    """Build a single-node plan stub with the requested ports.

    ``outputs=False`` (default) puts the ports on inputs; pass
    ``outputs=True`` to exercise the outputs branch.
    """
    schema = (
        NodeIOSchema(outputs=ports) if outputs else NodeIOSchema(inputs=ports)
    )
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        entry=True,
        terminal=True,
        io_schema=schema,
    )


def _plan(node: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=(node,))


class TestPortNamingConventionCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = PortNamingConventionCheck()

    # ------------------------------------------------------------------
    # Passing cases — canonical typed-port names
    # ------------------------------------------------------------------

    def test_canonical_names_do_not_raise(self) -> None:
        """Canonical names (``observation`` / ``decision`` / ``reflection``) pass."""
        node = _node(
            "thinker",
            (
                PortSpec(name="observation"),
                PortSpec(name="decision"),
                PortSpec(name="reflection"),
            ),
        )
        assert self.check.run(_plan(node), plan_id="test.plan") is None

    def test_outputs_are_also_checked(self) -> None:
        """Outputs branch is exercised — canonical output names pass."""
        node = _node(
            "thinker",
            (PortSpec(name="decision"), PortSpec(name="reflection")),
            outputs=True,
        )
        assert self.check.run(_plan(node), plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Failure cases — phase-alias suffixes
    # ------------------------------------------------------------------

    def test_perceive_payload_raises(self) -> None:
        """``perceive_payload`` ends in phase alias → reject."""
        node = _node("thinker", (PortSpec(name="perceive_payload"),))
        err = self.check.run(_plan(node), plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "perceive_payload" in str(err)
        assert "phase" in str(err).lower()

    def test_act_outcome_raises(self) -> None:
        """``act_outcome`` ends in phase alias → reject."""
        node = _node("thinker", (PortSpec(name="act_outcome"),))
        err = self.check.run(_plan(node), plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "act_outcome" in str(err)

    # ------------------------------------------------------------------
    # Failure cases — format violations
    # ------------------------------------------------------------------

    def test_pascal_case_raises(self) -> None:
        """``BadName`` (PascalCase) fails the snake_case regex → reject."""
        node = _node("thinker", (PortSpec(name="BadName"),))
        err = self.check.run(_plan(node), plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "BadName" in str(err)
        assert "snake_case" in str(err)

    def test_kebab_case_raises(self) -> None:
        """``bad-name`` (kebab-case) fails the snake_case regex → reject."""
        node = _node("thinker", (PortSpec(name="bad-name"),))
        err = self.check.run(_plan(node), plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "bad-name" in str(err)

    def test_name_with_space_raises(self) -> None:
        """``name with space`` fails the snake_case regex → reject."""
        node = _node("thinker", (PortSpec(name="name with space"),))
        err = self.check.run(_plan(node), plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert "name with space" in str(err)

    # ------------------------------------------------------------------
    # Surface check
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "port_naming_convention"
        assert self.check.label
