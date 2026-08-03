"""重构护栏 —— 组合根边界、lead 预算、ADR 索引、领域语言。"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ADR_DIR = _PROJECT_ROOT / "docs" / "adr"
_DEFAULTS_PATH = _PROJECT_ROOT / "lca" / "layer4_app" / "defaults.py"
_API_PATH = _PROJECT_ROOT / "lca" / "layer4_app" / "api.py"
_COMPOSER_PATH = _PROJECT_ROOT / "lca" / "layer4_app" / "composer.py"
_ADR_README = _ADR_DIR / "README.md"


class TestDefaultsNoObjectConstruction(unittest.TestCase):
    def test_defaults_no_object_construction(self) -> None:
        source = _DEFAULTS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_DEFAULTS_PATH))
        offenders: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in {"register_defaults"}:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        name = sub.func.id
                        if name.endswith("Transport") or name.startswith("build_"):
                            offenders.append(
                                f"{node.name}() 内调用 {name}() — 对象构造应留在 composer.py"
                            )
        self.assertFalse(offenders, "\n".join(offenders))


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


class TestLeadWallClockPropagation(unittest.TestCase):
    def test_lead_wall_clock_preserved(self) -> None:
        from unittest.mock import MagicMock

        from lca.layer3_agent.cognitive_agent import CognitiveAgent
        from lca.layer4_app.composer import _promote_lead
        from lca.layer4_app.policies import LeadBudgetPolicy

        runtime = MagicMock()
        role_profile = MagicMock()
        role_profile.role = "lead"
        lead = CognitiveAgent(runtime, role_profile, max_steps=10, max_wall_clock_seconds=900)
        promoted = _promote_lead(lead, LeadBudgetPolicy())
        self.assertEqual(promoted.max_wall_clock_seconds, 900)
        self.assertEqual(promoted.max_steps, 20)


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
    def test_agent_state_uses_consultation_not_progress_text(self) -> None:
        from lca.contracts.consultation import ConsultationState
        from lca.contracts.state import AgentState, Budget
        from lca.layer1_cognitive.member_status import InMemoryMemberStatus

        board = InMemoryMemberStatus(role_order=("a",))
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(),
            session=ConsultationState(member_status=board),
        )
        self.assertTrue(hasattr(state, "session"))
        self.assertFalse(hasattr(state, "member_status"))
        self.assertFalse(hasattr(state, "team_progress"))
        self.assertIn("a", board.as_prompt_text())

    def test_public_api_uses_run_and_compose(self) -> None:
        api = _API_PATH.read_text(encoding="utf-8")
        composer = _COMPOSER_PATH.read_text(encoding="utf-8")
        self.assertIn("class Team", api)
        self.assertIn("class TeamLead", api)
        self.assertIn("async def run", api)
        self.assertIn("def compose(", composer)
        self.assertIn("def compose_team(", composer)
        self.assertIn("await self._agent.run", api)
        self.assertNotIn("MultiAgentTeam", api)
        self.assertNotIn("assemble_agent", api)

    def test_must_consult_all_rewrites_early_respond(self) -> None:
        import asyncio

        from lca.contracts.consultation import ConsultationState
        from lca.contracts.decision import Decision
        from lca.contracts.state import AgentState, Budget
        from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
        from lca.layer1_cognitive.member_status import InMemoryMemberStatus

        board = InMemoryMemberStatus(role_order=("analyst",))
        state = AgentState(
            trace_id="t",
            task="ship",
            budget=Budget(),
            session=ConsultationState(member_status=board),
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
