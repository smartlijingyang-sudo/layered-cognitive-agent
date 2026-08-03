"""重构护栏 —— 防止组合根边界、supervisor 配置、ADR 索引再次腐化。"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ADR_DIR = _PROJECT_ROOT / "docs" / "adr"
_DEFAULTS_PATH = _PROJECT_ROOT / "lca" / "layer4_app" / "defaults.py"
_API_PATH = _PROJECT_ROOT / "lca" / "layer4_app" / "api.py"
_ADR_README = _ADR_DIR / "README.md"


class TestDefaultsNoObjectConstruction(unittest.TestCase):
    """defaults.py 只做注册，不构造可运行对象图。"""

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
                                f"{node.name}() 内调用 {name}() — 对象构造应留在 assembly.py"
                            )
        self.assertFalse(offenders, "\n".join(offenders))


class TestL4NoCompositionDecisionsOutsideAssembly(unittest.TestCase):
    """api.py 作为门面不得做 supervisor 预算 floor 等组合决策。"""

    def test_api_no_supervisor_budget_floors(self) -> None:
        source = _API_PATH.read_text(encoding="utf-8")
        forbidden_patterns = [
            r"_as_supervisor",
            r"_SUPERVISOR_MIN",
            r"max\s*\(\s*[^,]+\s*,\s*\d+\s*\).*max_steps",
        ]
        offenders = [pattern for pattern in forbidden_patterns if re.search(pattern, source)]
        self.assertFalse(
            offenders,
            f"api.py 含组合期决策模式: {offenders}",
        )


class TestSupervisorWallClockPropagation(unittest.TestCase):
    """MultiAgentTeam supervisor 的 max_wall_clock_seconds 不得被静默覆盖。"""

    def test_supervisor_wall_clock_preserved(self) -> None:
        from unittest.mock import MagicMock

        from lca.layer3_agent.cognitive_agent import CognitiveAgent
        from lca.layer4_app.assembly import _promote_supervisor
        from lca.layer4_app.policies import SupervisorBudgetPolicy

        runtime = MagicMock()
        role_profile = MagicMock()
        role_profile.role = "lead"
        supervisor = CognitiveAgent(runtime, role_profile, max_steps=10, max_wall_clock_seconds=900)
        promoted = _promote_supervisor(supervisor, SupervisorBudgetPolicy())
        self.assertEqual(promoted.max_wall_clock_seconds, 900)
        self.assertEqual(promoted.max_steps, 20)


class TestAdrIndexMatchesFilesystem(unittest.TestCase):
    """docs/adr/README.md 索引与目录内 ADR 编号一致且无重复。"""

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
    """Primary production names follow progressive-disclosure vocabulary."""

    def test_agent_state_uses_consultation_not_progress_text(self) -> None:
        from lca.contracts.consultation import ConsultationState
        from lca.contracts.state import AgentState, Budget
        from lca.layer1_cognitive.member_status import InMemoryMemberStatus

        board = InMemoryMemberStatus(role_order=("a",))
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(),
            consultation=ConsultationState(member_status=board),
        )
        self.assertTrue(hasattr(state, "consultation"))
        self.assertFalse(hasattr(state, "member_status"))
        self.assertFalse(hasattr(state, "team_progress"))
        self.assertFalse(hasattr(state, "team_progress_text"))
        self.assertIn("a", board.as_prompt_text())

    def test_public_api_uses_run_and_assemble_agent(self) -> None:
        api = (_PROJECT_ROOT / "lca" / "layer4_app" / "api.py").read_text(encoding="utf-8")
        assembly = (_PROJECT_ROOT / "lca" / "layer4_app" / "assembly.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("assemble_agent", api)
        self.assertNotIn("assemble_base_agent", api)
        self.assertIn("async def run", api)
        self.assertIn("def assemble_agent", assembly)
        self.assertIn("await self._agent.run", api)

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
            consultation=ConsultationState(member_status=board),
        )
        decision = Decision(
            decision_id="d1",
            action_type="respond",
            rationale="done",
            confidence=1.0,
            response_text="final",
        )
        out = asyncio.run(MustConsultAllMembers().enforce(state, decision))
        self.assertEqual(out.action_type, "delegate")
        assert out.delegations
        self.assertEqual(out.delegations[0].target_role, "analyst")


if __name__ == "__main__":
    unittest.main()
