"""LLMTeamCaster 金测与 CastingPlan → Team 编译（ADR-0042）。

用 ScriptedLLMAdapter 钉死 casting JSON schema 与白名单校验路径；
提示词模板改动若破坏输出格式，测试先于生产发现。
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from lca.contracts.models.team.team_coordination import LeadMandate, Pipeline
from lca.contracts.protocols.casting import (
    CastingError,
    CastingPlan,
    RoleCard,
    RoleIndexEntry,
    RoleNotFoundError,
    SelectedRole,
)
from lca.contracts.protocols.spec import LeadSpec
from lca.agent.role_library import FileRoleLibrary
from lca.application.api import Team
from lca.application.casting import (
    LLMTeamCaster,
    build_from_casting_plan,
    parse_casting_output,
    repair_invalid_role_ids,
)
from lca.plugins.seam_definitions.team_casting_prompt_renderer import BuiltinCastingPromptRenderer
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter


class _FixedLibrary:
    """测试用静态角色库（结构符合 RoleLibrary 协议）。"""

    def __init__(self) -> None:
        self._cards = {
            "marketing/content": RoleCard(
                "marketing/content", "内容专家", "marketing", "文案表达", "content body"
            ),
            "product/pm": RoleCard("product/pm", "产品经理", "product", "需求分析", "pm body"),
            "strategy/lead": RoleCard(
                "strategy/lead", "项目总监", "strategy", "统筹收口", "lead body"
            ),
        }

    def index(self) -> tuple[RoleIndexEntry, ...]:
        return tuple(
            RoleIndexEntry(c.role_id, c.title, c.department, c.summary)
            for c in sorted(self._cards.values(), key=lambda card: card.role_id)
        )

    def get(self, role_id: str) -> RoleCard:
        try:
            return self._cards[role_id]
        except KeyError as exc:
            raise RoleNotFoundError(role_id) from exc


def _plan_json(
    kind: str,
    role_ids: list[str],
    *,
    lead_role_id: str | None = None,
    hints: dict[str, str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "selected": [
            {"role_id": role_id, "task_hint": (hints or {}).get(role_id)} for role_id in role_ids
        ],
        "governance": {"kind": kind},
        "rationale": "scripted plan",
    }
    if lead_role_id is not None:
        payload["governance"]["lead_role_id"] = lead_role_id
    return json.dumps(payload, ensure_ascii=False)


def _caster() -> LLMTeamCaster:
    """Build the standard caster with its explicit prompt-content dependency."""

    return LLMTeamCaster(BuiltinCastingPromptRenderer())


def _caster_llm(*responses: str) -> ScriptedLLMAdapter:
    from lca.contracts.models.core.llm import LLMResponse

    return ScriptedLLMAdapter(
        {"caster": [LLMResponse(text=r, model="scripted-llm") for r in responses]},
        default_respond=False,
    )


class TestLLMTeamCaster(unittest.IsolatedAsyncioTestCase):
    async def test_cast_board_plan(self) -> None:
        llm = _caster_llm(
            _plan_json("board", ["strategy/lead", "product/pm"], lead_role_id="strategy/lead")
        )
        plan = await _caster().cast("评估新方案", _FixedLibrary(), llm)
        self.assertEqual(plan.governance_kind, "board")
        self.assertEqual(plan.lead_role_id, "strategy/lead")
        self.assertEqual([s.role_id for s in plan.selected], ["strategy/lead", "product/pm"])
        # 提示词携带 ROLE: caster 标记，脚本化替身按角色分发
        self.assertEqual(llm.calls[0][0], "caster")

    async def test_cast_auto_repairs_unknown_role_alias(self) -> None:
        library = FileRoleLibrary()
        llm = _caster_llm(
            _plan_json("pipeline", ["user-researcher", "product/product-manager"]),
        )
        plan = await _caster().cast("做用户研究", library, llm)
        self.assertEqual(
            [s.role_id for s in plan.selected],
            ["design/design-ux-researcher", "product/product-manager"],
        )
        self.assertEqual(len(llm.calls), 1)

    async def test_cast_retries_after_unknown_role_then_succeeds(self) -> None:
        llm = _caster_llm(
            _plan_json("pipeline", ["ghost/role", "product/pm"]),
            _plan_json("pipeline", ["marketing/content", "product/pm"]),
        )
        plan = await _caster().cast("写发布稿", _FixedLibrary(), llm)
        self.assertEqual([s.role_id for s in plan.selected], ["marketing/content", "product/pm"])
        self.assertEqual(len(llm.calls), 2)

    async def test_cast_raises_after_retry_exhausted(self) -> None:
        llm = _caster_llm(
            _plan_json("pipeline", ["zzz/qqqqwwwweeee-xxxxyyyy", "zzz/another-nope-role"]),
            _plan_json("pipeline", ["zzz/qqqqwwwweeee-xxxxyyyy", "zzz/another-nope-role"]),
        )
        with self.assertRaises(CastingError):
            await _caster().cast("写发布稿", _FixedLibrary(), llm)

    async def test_cast_rejects_unknown_governance_kind(self) -> None:
        llm = _caster_llm(
            _plan_json("hive_mind", ["product/pm", "strategy/lead"]),
            _plan_json("hive_mind", ["product/pm", "strategy/lead"]),
        )
        with self.assertRaises(CastingError):
            await _caster().cast("做方案", _FixedLibrary(), llm)

    async def test_cast_rejects_lead_kind_without_lead(self) -> None:
        llm = _caster_llm(
            _plan_json("board", ["strategy/lead", "product/pm"]),
            _plan_json("board", ["strategy/lead", "product/pm"]),
        )
        with self.assertRaises(CastingError):
            await _caster().cast("做决策", _FixedLibrary(), llm)

    async def test_cast_rejects_coordination_with_lead(self) -> None:
        llm = _caster_llm(
            _plan_json("pipeline", ["product/pm", "strategy/lead"], lead_role_id="strategy/lead"),
            _plan_json("pipeline", ["product/pm", "strategy/lead"], lead_role_id="strategy/lead"),
        )
        with self.assertRaises(CastingError):
            await _caster().cast("接力任务", _FixedLibrary(), llm)

    async def test_cast_rejects_single_role(self) -> None:
        llm = _caster_llm(
            _plan_json("pipeline", ["product/pm"]),
            _plan_json("pipeline", ["product/pm"]),
        )
        with self.assertRaises(CastingError):
            await _caster().cast("一个就够", _FixedLibrary(), llm)

    async def test_cast_rejects_invalid_json(self) -> None:
        llm = _caster_llm("完全不是 JSON", "还是不是 JSON")
        with self.assertRaises(CastingError):
            await _caster().cast("随便", _FixedLibrary(), llm)


class TestCastingRoleRepair(unittest.TestCase):
    def test_repair_user_researcher_alias(self) -> None:
        library = FileRoleLibrary()
        payload = {
            "selected": [
                {"role_id": "user-researcher"},
                {"role_id": "product/product-manager"},
            ],
            "governance": {"kind": "pipeline"},
        }
        repaired, replacements = repair_invalid_role_ids(payload, library)
        self.assertEqual(replacements, [("user-researcher", "design/design-ux-researcher")])
        plan, error = parse_casting_output(json.dumps(repaired, ensure_ascii=False), library)
        assert plan is not None
        self.assertEqual(error, "")
        self.assertEqual(
            [s.role_id for s in plan.selected],
            ["design/design-ux-researcher", "product/product-manager"],
        )


class TestBuildFromCastingPlan(unittest.TestCase):
    def test_lead_path_builds_team_with_mandate(self) -> None:
        plan = CastingPlan(
            selected=(
                SelectedRole(role_id="strategy/lead", task_hint="主持本次评估"),
                SelectedRole(role_id="product/pm"),
            ),
            governance_kind="consult",
            lead_role_id="strategy/lead",
            rationale="x",
        )
        team = build_from_casting_plan(
            plan,
            _FixedLibrary(),
            ScriptedLLMAdapter(),
            observability=InMemoryObservability(),
            tools=(),
        )
        self.assertIsInstance(team, Team)
        governance = team.spec.governance
        self.assertIsInstance(governance, LeadSpec)
        assert isinstance(governance, LeadSpec)
        self.assertEqual(governance.mandate, LeadMandate.CONSULT)
        self.assertEqual(governance.agent.profile.role, "项目总监")
        self.assertIn("主持本次评估", governance.agent.profile.goal)
        self.assertEqual([m.profile.role for m in team.spec.members], ["产品经理"])

    def test_coordination_path_builds_pipeline_in_selected_order(self) -> None:
        plan = CastingPlan(
            selected=(
                SelectedRole(role_id="product/pm", task_hint="先出需求要点"),
                SelectedRole(role_id="marketing/content"),
            ),
            governance_kind="pipeline",
        )
        team = build_from_casting_plan(
            plan,
            _FixedLibrary(),
            ScriptedLLMAdapter(),
            observability=InMemoryObservability(),
            tools=(),
        )
        self.assertIsInstance(team.spec.governance, Pipeline)
        self.assertEqual([m.profile.role for m in team.spec.members], ["产品经理", "内容专家"])
        self.assertIn("本次任务：先出需求要点", team.spec.members[0].profile.goal)
        # 无 task_hint 的成员 goal 回退为角色卡 summary
        self.assertEqual(team.spec.members[1].profile.goal, "文案表达")


if __name__ == "__main__":
    unittest.main()
