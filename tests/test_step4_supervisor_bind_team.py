"""Step 4 单元测试 —— Supervisor.bind_team / build_team_transport / TeamOrchestrator 接线。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import Observation
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.supervisor import Supervisor
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.defaults import build_team_transport

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_role(role: str, goal: str = "") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=goal or f"goal-{role}",
        backstory=f"backstory-{role}",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _make_member(role: str, return_output: str = "done") -> BaseAgent:
    runtime = MagicMock()
    member = BaseAgent(runtime, _make_role(role))
    member.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=Result(
            trace_id=f"trace-{role}",
            status="completed",
            output=return_output,
            final_state_ref="",
            total_steps=1,
            budget_used=None,  # type: ignore[arg-type]
        ),
    )
    return member


def _make_supervisor_with_runtime() -> tuple[Supervisor, MagicMock, MagicMock, MagicMock]:
    """返回 (supervisor, mock_runtime, mock_body, mock_reasoner)。"""
    mock_body = MagicMock()
    mock_body.transport = None

    mock_reasoner = MagicMock()
    mock_reasoner.team_roster = None

    mock_brain = MagicMock()
    mock_brain.reasoner = mock_reasoner

    mock_runtime = MagicMock()
    mock_runtime.body = mock_body
    mock_runtime.brain = mock_brain

    sup = Supervisor(mock_runtime, _make_role("supervisor"))
    return sup, mock_runtime, mock_body, mock_reasoner


# ---------------------------------------------------------------------------
# Supervisor.bind_team
# ---------------------------------------------------------------------------


class TestSupervisorBindTeam(unittest.IsolatedAsyncioTestCase):
    async def test_bind_team_sets_transport_on_body(self) -> None:
        sup, _, mock_body, _ = _make_supervisor_with_runtime()
        transport = InternalTransport()
        sup.bind_team(transport, "roster text")
        self.assertIs(mock_body.transport, transport)

    async def test_bind_team_sets_roster_on_reasoner(self) -> None:
        sup, _, _, mock_reasoner = _make_supervisor_with_runtime()
        transport = InternalTransport()
        sup.bind_team(transport, "- role: dev | goal: code")
        self.assertEqual(mock_reasoner.team_roster, "- role: dev | goal: code")

    async def test_bind_team_tolerates_body_without_transport_attr(self) -> None:
        """Body 是纯 Protocol 实例（没有 transport 属性）时不崩溃。"""
        mock_body = MagicMock(spec=[])  # 无任何属性
        mock_brain = MagicMock()
        mock_brain.reasoner = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.body = mock_body
        mock_runtime.brain = mock_brain

        sup = Supervisor(mock_runtime, _make_role("supervisor"))
        transport = InternalTransport()
        sup.bind_team(transport, "roster")
        # 不抛异常即通过

    async def test_bind_team_tolerates_brain_without_reasoner(self) -> None:
        """Brain 没有 reasoner 属性时不崩溃。"""
        mock_body = MagicMock()
        mock_body.transport = None
        mock_brain = MagicMock(spec=[])  # 无 reasoner
        mock_runtime = MagicMock()
        mock_runtime.body = mock_body
        mock_runtime.brain = mock_brain

        sup = Supervisor(mock_runtime, _make_role("supervisor"))
        transport = InternalTransport()
        sup.bind_team(transport, "roster")
        # 不抛异常即通过


# ---------------------------------------------------------------------------
# Supervisor.delegate 已删除
# ---------------------------------------------------------------------------


class TestDelegateRemoved(unittest.TestCase):
    def test_delegate_method_no_longer_exists(self) -> None:
        self.assertFalse(hasattr(Supervisor, "delegate"))


# ---------------------------------------------------------------------------
# build_team_transport (L4 factory)
# ---------------------------------------------------------------------------


class TestBuildTeamTransport(unittest.IsolatedAsyncioTestCase):
    async def test_registers_each_member_by_role(self) -> None:
        members = [_make_member("researcher"), _make_member("writer")]
        transport, _roster = build_team_transport(members)

        self.assertIsInstance(transport, InternalTransport)
        # 两个 role 都已注册
        self.assertIn("researcher", transport._directory)
        self.assertIn("writer", transport._directory)

    async def test_roster_contains_all_roles(self) -> None:
        members = [_make_member("dev"), _make_member("qa")]
        _, roster = build_team_transport(members)

        self.assertIn("dev", roster)
        self.assertIn("qa", roster)
        self.assertIn("goal-dev", roster)
        self.assertIn("goal-qa", roster)

    async def test_handler_returns_observation(self) -> None:
        members = [_make_member("worker", "result-output")]
        transport, _ = build_team_transport(members)

        handler = transport._directory["worker"]
        obs = await handler("do something")
        self.assertIsInstance(obs, Observation)
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "result-output")

    async def test_empty_members(self) -> None:
        transport, roster = build_team_transport([])
        self.assertIsInstance(transport, InternalTransport)
        self.assertEqual(len(transport._directory), 0)
        self.assertIn("无可用队友", roster)


# ---------------------------------------------------------------------------
# TeamOrchestrator._run_hierarchical 集成
# ---------------------------------------------------------------------------


class TestTeamOrchestratorHierarchical(unittest.IsolatedAsyncioTestCase):
    async def test_hierarchical_calls_bind_team_before_execute(self) -> None:
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, mock_body, mock_reasoner = _make_supervisor_with_runtime()
        sup.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Result(
                trace_id="t",
                status="completed",
                output="ok",
                final_state_ref="",
                total_steps=1,
                budget_used=None,  # type: ignore[arg-type]
            ),
        )

        transport, roster_desc = build_team_transport(members)
        orchestrator = TeamOrchestrator(
            members,
            config,
            supervisor=sup,
            transport=transport,
            roster_desc=roster_desc,
        )
        result = await orchestrator.run("build feature")

        # bind_team 应该被调用：body.transport 不再是 None
        self.assertIsInstance(mock_body.transport, InternalTransport)
        # reasoner.team_roster 应该被设置
        self.assertIn("dev", mock_reasoner.team_roster)
        # execute 应该被调用
        sup.execute.assert_awaited_once_with("build feature")
        self.assertEqual(result.output, "ok")

    async def test_hierarchical_without_transport_skips_bind(self) -> None:
        """不传 transport 时不报错（向后兼容）。"""
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, mock_body, _ = _make_supervisor_with_runtime()
        sup.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Result(
                trace_id="t",
                status="completed",
                output="ok",
                final_state_ref="",
                total_steps=1,
                budget_used=None,  # type: ignore[arg-type]
            ),
        )

        orchestrator = TeamOrchestrator(members, config, supervisor=sup)
        await orchestrator.run("task")

        # transport 应保持 None（没被 bind）
        self.assertIsNone(mock_body.transport)

    async def test_hierarchical_requires_supervisor(self) -> None:
        config = TeamConfig(process="hierarchical")
        orchestrator = TeamOrchestrator([], config, supervisor=None)
        with self.assertRaises(ValueError):
            await orchestrator.run("task")


if __name__ == "__main__":
    unittest.main()
