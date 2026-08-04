"""Routing 监督者 prompt 从账本渲染 MEMBER_REPORTS（ADR-0032）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from lca.contracts.delegation import DelegationResult
from lca.contracts.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.memory import MemoryRecord
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.routing import RoutingState
from lca.contracts.semantic_keys import META_ROLE, META_STEP
from lca.contracts.state import AgentState, Budget
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import (
    SupervisorReasoner,
    build_member_reports_text,
)


def _profile(role: str) -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=f"goal of {role}",
        backstory=f"backstory of {role}",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _ledger(role: str, subtask: str, output: str) -> DelegationResult:
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
        return (
            '{"action_type": "respond", "response_text": "ok", "rationale": "r", "confidence": 0.9}'
        )

    async def stream(self, prompt: str, **kwargs: object):
        yield await self.complete(prompt, **kwargs)


class TestMemberReportsText(unittest.TestCase):
    def test_empty_ledger(self) -> None:
        self.assertEqual(build_member_reports_text([]), "(尚无成员回报)")

    def test_success_entry_carries_attribution(self) -> None:
        text = build_member_reports_text([_ledger("Alice", "tech risk", "兼容性是核心风险")])
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


class TestRoutingPromptLedger(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_contains_member_reports_and_excludes_duplicate_context(self) -> None:
        llm = _CaptureLLM()
        reasoner = SupervisorReasoner(
            llm,  # type: ignore[arg-type]
            _profile("Lead"),
            tools_desc="(no tools available)",
            templates={"routing_prompt": load_builtin_prompt("routing_prompt")},
            allowed_actions_desc="1. delegate 2. respond",
        )
        routing = RoutingState(
            teammates=[_profile("Alice"), _profile("Bob")],
            assigned_roles=["Alice"],
            results=[_ledger("Alice", "tech risk", "兼容性是核心风险")],
        )
        state = AgentState(trace_id="t", task="probe", budget=Budget(), session=routing)
        # working memory 里另有一条委派记录 —— 账本视图下不得重复出现在 CONTEXT
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

        await reasoner.generate_candidates(state)

        prompt = llm.prompts[0]
        self.assertIn("MEMBER_REPORTS", prompt)
        self.assertIn("Alice | step 0 | 子任务: tech risk", prompt)
        self.assertIn("兼容性是核心风险", prompt)
        # CONTEXT 段不再重复渲染委派记录（账本是唯一事实视图）
        self.assertNotIn("Alice 已返回(step=0)", prompt)


if __name__ == "__main__":
    unittest.main()
