"""Regression coverage for Gate primitive semantic addresses."""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.logic_address import score_logic_address
from lca.harness.plugin_declaration import definition_from_plugin
from lca.plugins.gates.artifact_respond_injector import setup as artifact_respond_setup
from lca.plugins.gates.must_consult_all import setup as must_consult_all_setup
from lca.plugins.gates.progress_loop_detector import setup as progress_loop_setup
from lca.plugins.gates.terminal_respond import setup as terminal_respond_setup


def test_gate_primitives_publish_complete_g6_guard_addresses() -> None:
    """Gate contributions govern candidate decisions during the Think guard slot."""

    for setup in (
        artifact_respond_setup,
        must_consult_all_setup,
        progress_loop_setup,
        terminal_respond_setup,
    ):
        definition = definition_from_plugin(setup)
        address = definition.logic_address

        assert definition.functional_group is FunctionalGroup.G6_DECISION
        assert address is not None
        assert address.functional_group is FunctionalGroup.G6_DECISION
        assert address.control_slot is ControlSlot.THINK_GUARD
        assert score_logic_address(address).total == 100
