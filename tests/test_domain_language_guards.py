"""Guards: forbidden legacy team vocabulary is gone; domain language is public."""

from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import MagicMock

from lca.contracts.atoms.enums import DecisionGateName
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team_coordination import (
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

    def test_team_spec_shape(self) -> None:
        """TeamSpec 是团队形态唯一事实来源：字段面冻结，无旧模型残留字段。"""
        from lca.contracts.protocols.spec import TeamSpec

        names = {f.name for f in dataclasses.fields(TeamSpec)}
        self.assertEqual(
            names,
            {
                "members",
                "governance",
                "shared_memory_layers",
                "delegate_max_attempts",
                "observability",
            },
        )
        for legacy in ("strategy_key", "lead_mandate", "max_rounds", "process", "supervisor_mode"):
            self.assertNotIn(legacy, names)

    def test_governance_strategy_key_derivation(self) -> None:
        """strategy key 由 governance 单向派生（lead 与 coordination 同一入口）。"""
        from lca.contracts.protocols.spec import (
            AgentSpec,
            LeadSpec,
            strategy_key_for_governance,
        )

        self.assertEqual(strategy_key_for_governance(Pipeline()), STRATEGY_KEY_PIPELINE)
        agent_spec = AgentSpec(
            profile=RoleProfile(
                role="lead",
                goal="g",
                backstory="b",
                tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
            ),
            llm=MagicMock(),
        )
        lead = LeadSpec(agent=agent_spec, mandate=LeadMandate.BOARD)
        self.assertEqual(strategy_key_for_governance(lead), STRATEGY_KEY_LEAD)

    def test_mandate_gate_mapping(self) -> None:
        self.assertEqual(
            gate_name_for_mandate(LeadMandate.BOARD), DecisionGateName.MUST_CONSULT_ALL
        )
        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)

    def test_pipeline_strategy_key(self) -> None:
        from lca.contracts.models.team.team_coordination import strategy_key_for_coordination

        self.assertEqual(strategy_key_for_coordination(Pipeline()), STRATEGY_KEY_PIPELINE)
        self.assertEqual(STRATEGY_KEY_FAN_OUT, "fan_out")


if __name__ == "__main__":
    unittest.main()
