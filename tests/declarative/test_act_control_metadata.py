"""Regression coverage for declarative G6 Act-control contributions."""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.composition.logic_address import score_logic_address
from lca.harness.plugin_declaration import definition_from_plugin
from lca.plugins.control_contributions.act_authorize import setup as authorize_setup
from lca.plugins.control_contributions.act_budget import setup as budget_setup
from lca.plugins.control_contributions.act_constrain import setup as constrain_setup
from lca.plugins.control_contributions.act_execute import setup as execute_setup
from lca.plugins.control_contributions.act_safe_boundary import setup as safe_boundary_setup


def test_act_control_chain_has_complete_ordered_g6_addresses() -> None:
    """Each Act governance step has one precise semantic and control address."""

    expected = (
        (authorize_setup, ControlSlot.ACT_AUTHORIZE, "act.authorize", 0),
        (budget_setup, ControlSlot.ACT_BUDGET, "act.budget", 1),
        (constrain_setup, ControlSlot.ACT_CONSTRAIN, "act.constrain", 2),
        (execute_setup, ControlSlot.ACT_EXECUTE, "act.execute", 3),
        (safe_boundary_setup, ControlSlot.ACT_SAFE_BOUNDARY, "act.safe-boundary", 4),
    )

    for setup, slot, output, order in expected:
        definition = definition_from_plugin(setup)
        address = definition.logic_address

        assert definition.functional_group is FunctionalGroup.G6_DECISION
        assert address is not None
        assert address.functional_group is FunctionalGroup.G6_DECISION
        assert address.control_slot is slot
        assert score_logic_address(address).total == 100
        assert len(definition.spec.contributes) == 1
        contribution = definition.spec.contributes[0]
        assert contribution.output == output
        assert contribution.order == order
