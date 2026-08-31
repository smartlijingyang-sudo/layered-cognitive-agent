"""自由 routing 的 lead prompt 从 awareness 回报记录渲染 MEMBER_REPORTS。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from lca.cognition.brain.prompts import load_builtin_prompt
from lca.cognition.brain.reasoner import (
    PromptReasoner,
    build_member_reports_text,
)
from lca.contracts.atoms.enums import LLMStreamEventType, MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.semantic_keys import META_ROLE, META_STEP
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team_awareness import TeamAwareness


def _profile(role: str) -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=f"goal of {role}",
        backstory=f"backstory of {role}",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _result(role: str, subtask: str, output: str) -> DelegationResult:
    return DelegationResult(
        result_id=f"dres_{role}",
        target_role=role,
        subtask=subtask,
        output=output,
        success=True,
        error=None,
        task_id=f"task_{role}",
        step=0,
        returned_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )


class _CaptureLLM:
    name = "capture"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, prompt: str, **kwargs: object) -> str:
        self.prompts.append(prompt)
        return LLMResponse(
            text='{"action_type": "respond", "response_text": "ok", "rationale": "r", "confidence": 0.9}'
        )

    async def stream(self, prompt: str, **kwargs: object):
        response = await self.complete(prompt, **kwargs)
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


class TestMemberReportsText(unittest.TestCase):
    def test_empty_results(self) -> None:
        self.assertEqual(build_member_reports_text([]), "(尚无成员回报)")

    def test_success_entry_carries_attribution(self) -> None:
        text = build_member_reports_text([_result("Alice", "tech risk", "兼容性是核心风险")])
        self.assertIn("Alice", text)
        self.assertIn("tech risk", text)
        self.assertIn("兼容性是核心风险", text)
        self.assertIn("已返回", text)

    def test_failed_entry_is_flagged_retriable(self) -> None:
        failed = DelegationResult(
            result_id="dres_x",
            target_role="Bob",
            subtask="biz risk",
            output=None,
            success=False,
            error="timeout",
            task_id=None,
            step=0,
            returned_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        )
        text = build_member_reports_text([failed])
        self.assertIn("失败", text)
        self.assertIn("可重新委派", text)


class TestRoutingPromptMemberReports(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_contains_member_reports_and_excludes_duplicate_context(self) -> None:
        llm = _CaptureLLM()
        reasoner = PromptReasoner(
            llm,  # type: ignore[arg-type]
            _profile("Lead"),
            tools_desc="(no tools available)",
            templates={"routing_prompt": load_builtin_prompt("routing_prompt")},
        )
        awareness = TeamAwareness(
            teammates=[_profile("Alice"), _profile("Bob")],
            assigned_roles=["Alice"],
            results=[_result("Alice", "tech risk", "兼容性是核心风险")],
        )
        state = AgentState(trace_id="t", task="probe", budget=Budget(), team_awareness=awareness)
        # working memory 里另有一条委派记录 —— 回报记录视图下不得重复出现在 CONTEXT
        state.retrieved_context = [
            MemoryRecord(
                record_id="mem_1",
                content="兼容性是核心风险",
                memory_type=MemoryLayer.WORKING,
                importance=0.9,
                kind=MemoryRecordKind.DELEGATION_RESULT,
                metadata={META_ROLE: "Alice", META_STEP: 0},
            )
        ]

        await reasoner.generate_thoughts(state)

        prompt = llm.prompts[0]
        self.assertIn("MEMBER_REPORTS", prompt)
        self.assertIn("Alice | step 0 | 子任务: tech risk", prompt)
        self.assertIn("兼容性是核心风险", prompt)
        # CONTEXT 段不再重复渲染委派记录（回报记录是唯一事实视图）
        self.assertNotIn("Alice 已返回(step=0)", prompt)


if __name__ == "__main__":
    unittest.main()
