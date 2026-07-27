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
from lca.layer0_infra.transport.transport_registry import TransportRegistry
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


def _make_supervisor_with_runtime() -> tuple[Supervisor, MagicMock, TransportRegistry, MagicMock]:
    """返回 (supervisor, mock_runtime, transport_registry, mock_reasoner)。

    mock_runtime.configure() 模拟 CognitiveRuntime.configure() 的分发行为：
    transport → body.bind_transport() → registry.register()
    team_roster → brain.set_team_roster() → reasoner.team_roster = ...
    """
    registry = TransportRegistry()
    mock_body = MagicMock()
    mock_body.bind_transport = lambda t: registry.register(t)

    mock_reasoner = MagicMock()
    mock_reasoner.team_roster = None

    mock_brain = MagicMock()
    mock_brain.set_team_roster = lambda desc: setattr(mock_reasoner, "team_roster", desc)

    mock_runtime = MagicMock()
    mock_runtime.configure.side_effect = lambda **kw: (
        mock_body.bind_transport(kw["transport"]) if "transport" in kw else None,
        mock_brain.set_team_roster(kw["team_roster"]) if "team_roster" in kw else None,
    )

    sup = Supervisor(mock_runtime, _make_role("supervisor"))
    return sup, mock_runtime, registry, mock_reasoner


# ---------------------------------------------------------------------------
# Supervisor.bind_team
# ---------------------------------------------------------------------------


class TestSupervisorBindTeam(unittest.IsolatedAsyncioTestCase):
    async def test_bind_team_registers_transport_in_registry(self) -> None:
        sup, _, registry, _ = _make_supervisor_with_runtime()
        transport = InternalTransport()
        sup.bind_team(transport, "roster text")
        resolved = registry.resolve("internal")
        self.assertIs(resolved, transport)

    async def test_bind_team_sets_roster_on_reasoner(self) -> None:
        sup, _, _, mock_reasoner = _make_supervisor_with_runtime()
        transport = InternalTransport()
        sup.bind_team(transport, "- role: dev | goal: code")
        self.assertEqual(mock_reasoner.team_roster, "- role: dev | goal: code")

    async def test_bind_team_calls_runtime_configure(self) -> None:
        """bind_team 通过 runtime.configure() 分发，不再越层访问。"""
        sup, mock_runtime, _, _ = _make_supervisor_with_runtime()
        transport = InternalTransport()
        sup.bind_team(transport, "roster")
        mock_runtime.configure.assert_called_once_with(transport=transport, team_roster="roster")

    async def test_bind_team_tolerates_body_without_bind_transport(self) -> None:
        """Body 没有 bind_transport 方法时，CognitiveRuntime.configure() hasattr 跳过。"""
        mock_body = MagicMock(spec=[])
        mock_brain = MagicMock()
        mock_brain.set_team_roster = MagicMock()
        mock_runtime = MagicMock()

        def _configure(**capabilities: object) -> None:
            if "transport" in capabilities and hasattr(mock_body, "bind_transport"):
                mock_body.bind_transport(capabilities["transport"])
            if "team_roster" in capabilities and hasattr(mock_brain, "set_team_roster"):
                mock_brain.set_team_roster(capabilities["team_roster"])

        mock_runtime.configure = _configure

        sup = Supervisor(mock_runtime, _make_role("supervisor"))
        transport = InternalTransport()
        sup.bind_team(transport, "roster")
        mock_brain.set_team_roster.assert_called_once_with("roster")

    async def test_bind_team_tolerates_brain_without_set_team_roster(self) -> None:
        """Brain 没有 set_team_roster 方法时，CognitiveRuntime.configure() hasattr 跳过。"""
        registry = TransportRegistry()
        mock_body = MagicMock()
        mock_body.bind_transport = lambda t: registry.register(t)
        mock_brain = MagicMock(spec=[])
        mock_runtime = MagicMock()

        def _configure(**capabilities: object) -> None:
            if "transport" in capabilities and hasattr(mock_body, "bind_transport"):
                mock_body.bind_transport(capabilities["transport"])
            if "team_roster" in capabilities and hasattr(mock_brain, "set_team_roster"):
                mock_brain.set_team_roster(capabilities["team_roster"])

        mock_runtime.configure = _configure

        sup = Supervisor(mock_runtime, _make_role("supervisor"))
        transport = InternalTransport()
        sup.bind_team(transport, "roster")
        self.assertIn("internal", registry)


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

        sup, _, registry, mock_reasoner = _make_supervisor_with_runtime()
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

        self.assertIsInstance(registry.resolve("internal"), InternalTransport)
        self.assertIn("dev", mock_reasoner.team_roster)
        sup.execute.assert_awaited_once_with("build feature")
        self.assertEqual(result.output, "ok")

    async def test_hierarchical_without_transport_skips_bind(self) -> None:
        """不传 transport 时不报错（向后兼容）。"""
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, registry, _ = _make_supervisor_with_runtime()
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

        self.assertEqual(registry.list_protocols(), [])

    async def test_hierarchical_requires_supervisor(self) -> None:
        config = TeamConfig(process="hierarchical")
        orchestrator = TeamOrchestrator([], config, supervisor=None)
        with self.assertRaises(ValueError):
            await orchestrator.run("task")


if __name__ == "__main__":
    unittest.main()
