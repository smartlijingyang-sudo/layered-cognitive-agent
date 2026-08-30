"""Regression coverage for the G7 execution primitive boundary."""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.composition.logic_address import score_logic_address
from lca.harness.plugin_declaration import definition_from_plugin
from lca.plugins.body.safe_executor import setup as safe_executor_setup
from lca.plugins.body.simple import setup as simple_body_setup
from lca.plugins.providers.action_handlers import setup as action_handler_setup
from lca.plugins.providers.tool_batch_execution_policy import setup as tool_batch_policy_setup


def test_execution_primitives_publish_complete_g7_logic_addresses() -> None:
    """Each production execution primitive has one readable governance address."""

    expected_slots = (
        (simple_body_setup, ControlSlot.ACT_EXECUTE),
        (safe_executor_setup, ControlSlot.ACT_SAFE_BOUNDARY),
        (tool_batch_policy_setup, ControlSlot.ACT_EXECUTE),
        (action_handler_setup, ControlSlot.ACT_EXECUTE),
    )

    for setup, slot in expected_slots:
        definition = definition_from_plugin(setup)
        address = definition.logic_address

        assert definition.functional_group is FunctionalGroup.G7_EXECUTION
        assert address is not None
        assert address.functional_group is FunctionalGroup.G7_EXECUTION
        assert address.control_slot is slot
        assert score_logic_address(address).total == 100
