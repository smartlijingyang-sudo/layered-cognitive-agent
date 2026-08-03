"""Guards: forbidden legacy team vocabulary is gone; domain language is public."""

from __future__ import annotations

import unittest

from lca.contracts.enums import DecisionGateName
from lca.contracts.role_team import TeamConfig
from lca.contracts.team_coordination import (
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PIPELINE,
    LeadMandate,
    Pipeline,
    gate_name_for_mandate,
)


class TestDomainLanguagePublicSurface(unittest.TestCase):
    def test_lca_exports_domain_names_only(self) -> None:
        import lca

        for good in ("Agent", "Team", "TeamLead", "LeadMandate", "Pipeline", "FanOut"):
            self.assertTrue(hasattr(lca, good), good)
        for bad in (
            "MultiAgentTeam",
            "Recipe",
            "TeamProcess",
            "SupervisorMode",
            "Assembly",
            "OrchestrationFamily",
        ):
            self.assertFalse(hasattr(lca, bad), bad)

    def test_no_legacy_modules(self) -> None:
        import importlib

        for mod in (
            "lca.contracts.orchestration_taxonomy",
            "lca.contracts.supervisor_mode",
            "lca.layer4_app.assembly",
        ):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module(mod)

    def test_team_config_shape(self) -> None:
        cfg = TeamConfig(strategy_key=STRATEGY_KEY_LEAD, lead_mandate=LeadMandate.BOARD)
        self.assertEqual(cfg.strategy_key, STRATEGY_KEY_LEAD)
        self.assertIs(cfg.lead_mandate, LeadMandate.BOARD)
        self.assertFalse(hasattr(cfg, "process"))
        self.assertFalse(hasattr(cfg, "supervisor_mode"))

    def test_mandate_gate_mapping(self) -> None:
        self.assertEqual(
            gate_name_for_mandate(LeadMandate.BOARD), DecisionGateName.MUST_CONSULT_ALL
        )
        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)

    def test_pipeline_strategy_key(self) -> None:
        from lca.contracts.team_coordination import strategy_key_for_coordination

        self.assertEqual(strategy_key_for_coordination(Pipeline()), STRATEGY_KEY_PIPELINE)
        self.assertEqual(STRATEGY_KEY_FAN_OUT, "fan_out")


if __name__ == "__main__":
    unittest.main()
