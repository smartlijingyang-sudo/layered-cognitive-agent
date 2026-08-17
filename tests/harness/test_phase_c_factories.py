"""Phase C integration tests - CognitiveLoopFactory and ReplayLoop."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lca.contracts.harness.agent import AgentOptions
from lca.harness.kernel.scope import ScopedPluginHost
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore
from lca.plugins.loop_cognitive import build_cognitive_live_agent
from lca.plugins.loop_replay import ReplayLiveAgent, ReplayLoopFactory


@pytest.fixture
def tmp_path(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def scope(tmp_path: Path) -> ScopedPluginHost:
    """Create a scope with mock dependencies."""
    root = ScopedPluginHost(None, "global", "test")

    # Mock dependencies
    brain = MagicMock()
    brain.think = MagicMock(return_value=None)
    brain.reflect = MagicMock(return_value=None)

    body = MagicMock()
    body.act = MagicMock(return_value=None)

    memory = MagicMock()
    memory.perceive = MagicMock(return_value=None)
    memory.update = MagicMock(return_value=None)

    state_store = MagicMock()
    state_store.save = MagicMock(return_value="ref")
    state_store.load = MagicMock(return_value=None)

    stop_rule = MagicMock()
    stop_rule.decide = MagicMock(return_value=MagicMock(should_stop=True, status=None))

    hooks = MagicMock()
    hooks.trigger = MagicMock(return_value=None)

    # Create session store
    from lca.contracts.harness.session import SessionHeader

    persistence = JsonlSessionPersistence(tmp_path / "session.jsonl")
    header = SessionHeader(version=1, id="test-session", created_at=0)
    session_store = SessionStore(header, persistence=persistence)

    # Mock middleware registry
    middleware_registry = MagicMock()
    middleware_registry.run = MagicMock(return_value=None)

    # Create a handle to register services
    from lca.layer0_infra.plugin.kernel._handle import PluginHandle
    from lca.layer0_infra.plugin.kernel._spec import PluginSpec

    spec = PluginSpec(name="test", apply=lambda ctx, cfg: None, provides="test")
    handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
    root.host.register_handle(handle)

    # Register dependencies using host.provide()
    root.host.provide(handle, "brain", brain)
    root.host.provide(handle, "body", body)
    root.host.provide(handle, "memory", memory)
    root.host.provide(handle, "state_store", state_store)
    root.host.provide(handle, "stop_rule", stop_rule)
    root.host.provide(handle, "hooks", hooks)
    root.host.provide(handle, "session_store", session_store)
    root.host.provide(handle, "middleware_registry", middleware_registry)

    return root


class TestCognitiveLoopBuilder:
    def test_build_cognitive_live_agent(self, scope: ScopedPluginHost, tmp_path: Path):
        """Test that build_cognitive_live_agent creates an agent."""
        from lca.contracts.harness.session import SessionHeader

        persistence = JsonlSessionPersistence(tmp_path / "agent.jsonl")
        header = SessionHeader(version=1, id="test-agent", created_at=0)
        store = SessionStore(header, persistence=persistence)
        inbox = MagicMock()

        handle = build_cognitive_live_agent(
            store=store,
            inbox=inbox,
            identity_id="test-agent",
            options={"max_steps": 5},
            plugin_scope=scope,
        )
        assert handle is not None
        assert handle.agent is not None
        assert handle.agent.session_id == "test-agent"

    def test_agent_has_required_methods(self, scope: ScopedPluginHost, tmp_path: Path):
        """Test that created agent has all required methods per LiveAgent protocol."""
        from lca.contracts.harness.session import SessionHeader

        persistence = JsonlSessionPersistence(tmp_path / "agent2.jsonl")
        header = SessionHeader(version=1, id="test-agent2", created_at=0)
        store = SessionStore(header, persistence=persistence)
        inbox = MagicMock()

        handle = build_cognitive_live_agent(
            store=store,
            inbox=inbox,
            identity_id="test-agent2",
            options={"max_steps": 5},
            plugin_scope=scope,
        )
        agent = handle.agent

        # Check required methods exist per LiveAgent protocol
        assert hasattr(agent, "id")
        assert hasattr(agent, "session_id")
        assert hasattr(agent, "status")
        assert hasattr(agent, "followup")
        assert hasattr(agent, "steer")
        assert hasattr(agent, "inject")
        assert hasattr(agent, "cancel")
        assert hasattr(agent, "when_idle")


class TestReplayLoopFactory:
    def test_create_replay_agent(self, scope: ScopedPluginHost, tmp_path: Path):
        """Test that ReplayLoopFactory creates a replay agent."""
        factory = ReplayLoopFactory()
        options = AgentOptions()

        async def _test():
            handle = await factory.create(scope, "replay-session", options)
            assert handle is not None
            assert handle.agent is not None
            assert isinstance(handle.agent, ReplayLiveAgent)
            assert handle.agent.session_id == "replay-session"

        asyncio.run(_test())

    def test_replay_agent_always_idle(self, scope: ScopedPluginHost, tmp_path: Path):
        """Test that replay agent is always idle."""
        factory = ReplayLoopFactory()
        options = AgentOptions()

        async def _test():
            handle = await factory.create(scope, "replay-session", options)
            agent = handle.agent

            assert agent.status == "idle"

            # when_idle should complete immediately
            await agent.when_idle()

        asyncio.run(_test())

    def test_replay_followup_returns_empty_on_no_events(
        self, scope: ScopedPluginHost, tmp_path: Path
    ):
        """Test that followup returns empty receipt when no events exist."""
        factory = ReplayLoopFactory()
        options = AgentOptions()

        async def _test():
            handle = await factory.create(scope, "replay-session", options)
            agent = handle.agent

            receipt = await agent.followup("test message")
            assert receipt.message_id == ""
            assert receipt.session_id == "replay-session"
            assert receipt.seq == -1

        asyncio.run(_test())


class TestAgentStateProjection:
    def test_init_creates_empty_state(self):
        """Test that init creates an empty AgentState."""
        from lca.harness.projection.agent_state import AgentStateProjection

        projection = AgentStateProjection()
        state = projection.init()

        assert state.trace_id == ""
        assert state.step == 0
        assert state.status == "working"

    def test_view_returns_serializable_dict(self):
        """Test that view returns a serializable dictionary."""
        from lca.contracts.models.core.lifecycle import TaskStatus
        from lca.harness.projection.agent_state import AgentStateProjection

        projection = AgentStateProjection()
        state = projection.init()
        state.trace_id = "test-trace"
        state.step = 5
        state.status = TaskStatus.COMPLETED

        view = projection.view(state)

        assert view["trace_id"] == "test-trace"
        assert view["step"] == 5
        assert view["status"] == "completed"
        assert isinstance(view, dict)
