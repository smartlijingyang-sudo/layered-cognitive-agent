"""Regression coverage for Sensor primitive semantic addresses."""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.logic_address import score_logic_address
from lca.harness.plugin_declaration import definition_from_plugin
from lca.plugins.sensors.clock import setup as clock_setup
from lca.plugins.sensors.inbox_facts import setup as inbox_facts_setup
from lca.plugins.sensors.skill_catalog import setup as skill_catalog_setup
from lca.plugins.sensors.team_inbox import setup as team_inbox_setup
from lca.plugins.sensors.workspace_artifacts import setup as workspace_artifacts_setup
from lca.plugins.sensors.workspace_instructions import setup as workspace_instructions_setup


def test_sensor_primitives_publish_complete_context_addresses() -> None:
    """Sensors separate G2 spacetime from G4 trusted-context grounding."""

    expected = (
        (clock_setup, FunctionalGroup.G2_SPACETIME),
        (inbox_facts_setup, FunctionalGroup.G4_PERCEPTION),
        (skill_catalog_setup, FunctionalGroup.G4_PERCEPTION),
        (team_inbox_setup, FunctionalGroup.G4_PERCEPTION),
        (workspace_artifacts_setup, FunctionalGroup.G4_PERCEPTION),
        (workspace_instructions_setup, FunctionalGroup.G4_PERCEPTION),
    )

    for setup, group in expected:
        definition = definition_from_plugin(setup)
        address = definition.logic_address

        assert definition.functional_group is group
        assert address is not None
        assert address.functional_group is group
        assert address.control_slot is ControlSlot.PERCEIVE_CONTEXT
        assert score_logic_address(address).total == 100
