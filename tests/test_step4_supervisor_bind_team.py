"""Step 4 单元测试 —— TeamOrchestrator 接线 / build_team_transport。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.decision import Observation
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols.capabilities import AcceptsTeammates, HasChannel
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.contracts.state import Budget
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.assembly import build_team_transport
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()

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


def _make_member(role: str, return_output: str = "done") -> CognitiveAgent:
    runtime = MagicMock()
    member = CognitiveAgent(runtime, _make_role(role))
    result = Result(
        trace_id=f"trace-{role}",
        status=TaskStatus.COMPLETED,
        output=return_output,
        final_state_ref="",
        total_steps=1,
        budget_used=Budget(),
    )
    member.run = AsyncMock(return_value=result)  # type: ignore[method-assign]
    return member


class _BindableBody(HasChannel):
    """测试用 Body：实现 HasChannel 协议。"""

    def __init__(self, registry: TransportRegistry) -> None:
        self._registry = registry

    def bind_channel(self, transport: object) -> None:
        # 测试桩：TransportRegistry.register 期望 AgentTransport，此处故意泛化
        self._registry.register(transport)  # type: ignore[arg-type]  # 测试桩放宽类型


class _AcceptsTeammatesBrain(AcceptsTeammates):
    """测试用 Brain：实现 AcceptsTeammates 协议。"""

    def __init__(self) -> None:
        self.teammates_text: str | None = None

    def set_teammates(self, teammates_text: str) -> None:
        self.teammates_text = teammates_text


def _make_supervisor_with_runtime() -> tuple[
    CognitiveAgent, MagicMock, TransportRegistry, _AcceptsTeammatesBrain
]:
    """返回 (supervisor, mock_runtime, transport_registry, brain)。"""
    registry = TransportRegistry()
    mock_body = _BindableBody(registry)
    mock_brain = _AcceptsTeammatesBrain()

    mock_runtime = MagicMock()
    mock_runtime.body = mock_body
    mock_runtime.brain = mock_brain
    mock_runtime.memory = MagicMock()

    sup = CognitiveAgent(mock_runtime, _make_role("supervisor"))
    return sup, mock_runtime, registry, mock_brain


# ---------------------------------------------------------------------------
# TeamOrchestrator 绑定 Supervisor 能力
# ---------------------------------------------------------------------------


class TestTeamOrchestratorBindsSupervisor(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_binds_transport_to_body(self) -> None:
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, registry, _ = _make_supervisor_with_runtime()
        _ok = Result(
            trace_id="t",
            status=TaskStatus.COMPLETED,
            output="ok",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
        )
        sup.run = AsyncMock(return_value=_ok)  # type: ignore[method-assign]

        transport, teammates_text = build_team_transport(members)
        orchestrator = TeamOrchestrator(
            members,
            config,
            supervisor=sup,
            transport=transport,
            teammates_text=teammates_text,
        )
        await orchestrator.run("build feature")

        self.assertIsInstance(registry.resolve("internal"), InternalTransport)

    async def test_orchestrator_sets_roster_on_brain(self) -> None:
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, _, mock_brain = _make_supervisor_with_runtime()
        _ok = Result(
            trace_id="t",
            status=TaskStatus.COMPLETED,
            output="ok",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
        )
        sup.run = AsyncMock(return_value=_ok)  # type: ignore[method-assign]

        transport, teammates_text = build_team_transport(members)
        orchestrator = TeamOrchestrator(
            members,
            config,
            supervisor=sup,
            transport=transport,
            teammates_text=teammates_text,
        )
        await orchestrator.run("build feature")

        self.assertIn("dev", mock_brain.teammates_text)

    async def test_orchestrator_without_transport_skips_bind(self) -> None:
        """不传 transport 时不报错（向后兼容）。"""
        members = [_make_member("dev")]
        config = TeamConfig(process="hierarchical")

        sup, _, registry, _ = _make_supervisor_with_runtime()
        _ok = Result(
            trace_id="t",
            status=TaskStatus.COMPLETED,
            output="ok",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
        )
        sup.run = AsyncMock(return_value=_ok)  # type: ignore[method-assign]

        orchestrator = TeamOrchestrator(members, config, supervisor=sup)
        await orchestrator.run("task")

        self.assertEqual(registry.list_protocols(), [])


# ---------------------------------------------------------------------------
# Supervisor.delegate 已删除
# ---------------------------------------------------------------------------


class TestDelegateRemoved(unittest.TestCase):
    def test_delegate_method_no_longer_exists(self) -> None:
        self.assertFalse(hasattr(CognitiveAgent, "delegate"))


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
# TeamOrchestrator 基础
# ---------------------------------------------------------------------------


class TestTeamOrchestratorBasic(unittest.IsolatedAsyncioTestCase):
    async def test_hierarchical_requires_supervisor(self) -> None:
        config = TeamConfig(process="hierarchical")
        orchestrator = TeamOrchestrator([], config, supervisor=None)
        with self.assertRaises(ValueError):
            await orchestrator.run("task")


if __name__ == "__main__":
    unittest.main()
