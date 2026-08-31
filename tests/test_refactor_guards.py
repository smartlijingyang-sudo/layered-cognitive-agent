"""重构护栏 —— 组合根边界、lead 预算、ADR 索引、领域语言。"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ADR_DIR = _PROJECT_ROOT / "docs" / "adr"
_API_PATH = _PROJECT_ROOT / "lca" / "application" / "api.py"
_SPAWN_PATH = _PROJECT_ROOT / "lca" / "application" / "spawn.py"
_DEFAULTS_PATH = _PROJECT_ROOT / "lca" / "application" / "defaults.py"
_ADR_README = _ADR_DIR / "README.md"


class TestSpawnNoConcreteServices(unittest.TestCase):
    """ADR-0062 PR-4: spawn.py AST must not import concrete service fallbacks."""

    def test_defaults_py_deleted(self) -> None:
        self.assertFalse(_DEFAULTS_PATH.exists(), "defaults.py must be deleted (ADR-0062 PR-4)")

    def test_spawn_no_concrete_service_imports(self) -> None:
        source = _SPAWN_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_SPAWN_PATH))
        forbidden = {
            "SimpleBody",
            "PerceiveService",
            "build_default_registries",
            "register_builtin_sensors",
            "ToolsService",
            "TransportService",
            "SimpleSafeExecutor",
            "DefaultStopPolicy",
            "MustConsultAllMembers",
        }
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[-1])
        offenders = sorted(forbidden & imported)
        self.assertFalse(
            offenders,
            f"spawn.py still imports concrete fallbacks: {offenders}",
        )


class TestL4ApiIsThinFacade(unittest.TestCase):
    def test_api_no_lead_budget_floors(self) -> None:
        source = _API_PATH.read_text(encoding="utf-8")
        forbidden_patterns = [
            r"_as_supervisor",
            r"_promote_lead",
            r"_SUPERVISOR_MIN",
            r"max\s*\(\s*[^,]+\s*,\s*\d+\s*\).*max_steps",
        ]
        offenders = [pattern for pattern in forbidden_patterns if re.search(pattern, source)]
        self.assertFalse(offenders, f"api.py 含组合期决策模式: {offenders}")


class TestNoProcessLevelComposerSingleton(unittest.TestCase):
    """ADR-0033：门面不得持有进程级 composer 单例（全局可变状态）。"""

    def test_no_global_composer_in_facade_or_spawn(self) -> None:
        offenders: list[str] = []
        for path in (_API_PATH, _SPAWN_PATH):
            source = path.read_text(encoding="utf-8")
            if re.search(r"^\s*global\s+", source, re.MULTILINE):
                offenders.append(f"{path.name} 含 global 语句")
            if "_get_default_composer" in source:
                offenders.append(f"{path.name} 引用 _get_default_composer")
        self.assertFalse(offenders, "\n".join(offenders))


class TestSpawnNoClosedGraphExcavation(unittest.TestCase):
    """ADR-0033：spawn 只从声明式 spec 组装，禁止从成品图反向挖零件。"""

    def test_no_excavation_patterns(self) -> None:
        source = _SPAWN_PATH.read_text(encoding="utf-8")
        forbidden_patterns = [
            r"_tools_from_agent",
            r"_llm_from_agent",
            r"_obs_from_agent",
            r"\._entries",
            r"\.reasoner\.llm",
            r"getattr\(\s*runtime",
        ]
        offenders = [pattern for pattern in forbidden_patterns if re.search(pattern, source)]
        self.assertFalse(offenders, f"spawn.py 含封闭图挖掘反模式: {offenders}")


class TestLeadWallClockPropagation(unittest.TestCase):
    def test_lead_wall_clock_preserved(self) -> None:
        from unittest.mock import MagicMock

        from lca.agent.cognitive_agent import CognitiveAgent
        from lca.application.policies import LeadBudgetPolicy
        from lca.application.spawn import promote_lead
        from lca.harness.observability.assemble import make_minimal_bound

        runtime = MagicMock()
        role_profile = MagicMock()
        role_profile.role = "lead"
        lead = CognitiveAgent(
            runtime,
            role_profile,
            make_minimal_bound(),
            max_steps=10,
            max_wall_clock_seconds=900,
        )
        promoted = promote_lead(lead, LeadBudgetPolicy())
        self.assertEqual(promoted.max_wall_clock_seconds, 900)
        self.assertEqual(promoted.max_steps, 20)


class TestModeCatalogKeyParity(unittest.TestCase):
    """ADR-0040：生产 mode_catalog 与测试 harness 的 mode key 集合必须一致。"""

    def test_harness_modes_match_gateway_catalog(self) -> None:
        import gateway.modes as gateway_catalog

        import tests.harness.modes as harness_modes_mod

        self.assertEqual(set(gateway_catalog.ALL_MODES), set(harness_modes_mod.ALL_MODES))


class TestAdrIndexMatchesFilesystem(unittest.TestCase):
    def test_adr_index_matches_filesystem(self) -> None:
        adr_files = sorted(_ADR_DIR.glob("*.md"))
        file_numbers: list[str] = []
        for path in adr_files:
            if path.name == "README.md":
                continue
            match = re.match(r"^(\d{4})-", path.name)
            self.assertIsNotNone(match, f"ADR 文件名不符合 NNNN- 前缀: {path.name}")
            file_numbers.append(match.group(1))

        duplicates = {n for n in file_numbers if file_numbers.count(n) > 1}
        self.assertFalse(duplicates, f"ADR 编号重复: {sorted(duplicates)}")

        readme = _ADR_README.read_text(encoding="utf-8")
        indexed = set(re.findall(r"\[(\d{4})\]", readme))
        filesystem = set(file_numbers)
        # 0030 may not be in README yet — allow missing until ADR written
        missing_in_readme = filesystem - indexed
        extra_in_readme = indexed - filesystem
        self.assertFalse(
            missing_in_readme,
            f"README 缺少 ADR 索引: {sorted(missing_in_readme)}",
        )
        self.assertFalse(
            extra_in_readme,
            f"README 索引指向不存在的 ADR: {sorted(extra_in_readme)}",
        )


class TestProgressiveDisclosureVocabulary(unittest.TestCase):
    def test_agent_state_uses_team_awareness_not_progress_text(self) -> None:
        from lca.cognition.member_status import InMemoryMemberStatus
        from lca.contracts.models.core.state import AgentState, Budget
        from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness

        board = InMemoryMemberStatus(role_order=("a",))
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(),
            team_awareness=TeamAwareness(
                consult_duty=ConsultDuty(member_status=board, max_attempts=3)
            ),
        )
        self.assertTrue(hasattr(state, "team_awareness"))
        self.assertFalse(hasattr(state, "member_status"))
        self.assertFalse(hasattr(state, "team_progress"))
        self.assertIn("a", board.as_prompt_text())

    def test_public_api_uses_run_and_spawn(self) -> None:
        api = _API_PATH.read_text(encoding="utf-8")
        spawn = _SPAWN_PATH.read_text(encoding="utf-8")
        self.assertIn("class Team", api)
        self.assertIn("class TeamLead", api)
        self.assertIn("async def run", api)
        self.assertIn("def spawn_agent(", spawn)
        self.assertIn("def spawn_team(", spawn)
        self.assertIn("await self._agent.run", api)
        self.assertNotIn("MultiAgentTeam", api)
        self.assertNotIn("AgentComposer", api)
        self.assertNotIn("assemble_agent", api)

    def test_must_consult_all_rewrites_early_respond(self) -> None:
        import asyncio

        from lca.cognition.brain.decision_gates import MustConsultAllMembers
        from lca.cognition.member_status import InMemoryMemberStatus
        from lca.contracts.models.core.decision import Decision
        from lca.contracts.models.core.state import AgentState, Budget
        from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness

        board = InMemoryMemberStatus(role_order=("analyst",))
        state = AgentState(
            trace_id="t",
            task="ship",
            budget=Budget(),
            team_awareness=TeamAwareness(
                consult_duty=ConsultDuty(member_status=board, max_attempts=3)
            ),
        )
        gate = MustConsultAllMembers()
        early = Decision(
            decision_id="d1",
            action_type="respond",
            rationale="done",
            confidence=1.0,
            response_text="ok",
        )
        rewritten = asyncio.run(gate.enforce(state, early))
        self.assertEqual(rewritten.action_type, "delegate")
