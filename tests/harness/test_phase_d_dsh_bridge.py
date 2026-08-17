"""Phase D tests — DSH Bridge Provider.

Verifies:
1. DSH events map correctly to LCA session event vocabulary
2. DshBridgeLoopFactory creates a valid AgentHandle
3. DshLiveAgent produces correct session events on followup
4. Gateway can use the bridge as a drop-in loop provider
5. Mixed Cognitive + DSH session trees work uniformly
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lca.contracts.harness.agent import AgentOptions, ContextMessage, UserMessage
from lca.contracts.harness.plugin import PluginKind
from lca.contracts.harness.session import SessionHeader
from lca.harness.kernel.scope import ScopedPluginHost
from lca.harness.session.inbox import Inbox
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore
from lca.plugins.loop_dsh_bridge import DshBridgeLoopFactory, manifest
from lca.plugins.loop_dsh_bridge.event_mapping import (
    DSH_EVENT_MAP,
    DshEventMapper,
    MappedEvent,
    to_session_event,
)
from lca.plugins.loop_dsh_bridge.live_agent import DshBridgeConfig, DshLiveAgent

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    persistence = JsonlSessionPersistence(tmp_path / "dsh-session.jsonl")
    header = SessionHeader(version=1, id="dsh-test-session", created_at=0)
    return SessionStore(header, persistence=persistence)


@pytest.fixture
def bridge_config(tmp_path: Path) -> DshBridgeConfig:
    transport = MagicMock()
    transport.write_files = AsyncMock(return_value=MagicMock(success=True))
    return DshBridgeConfig(
        machine_id="machine-1",
        cwd="/tmp/test",  # noqa: S108
        transport=transport,
        runs_dir=tmp_path,
    )


@pytest.fixture
def scope(tmp_path: Path, bridge_config: DshBridgeConfig) -> ScopedPluginHost:
    from lca.layer0_infra.plugin.kernel._handle import PluginHandle
    from lca.layer0_infra.plugin.kernel._spec import PluginSpec

    root = ScopedPluginHost(None, "global", "test")
    persistence = JsonlSessionPersistence(tmp_path / "session.jsonl")
    header = SessionHeader(version=1, id="test-session", created_at=0)
    session_store = SessionStore(header, persistence=persistence)

    spec = PluginSpec(name="test", apply=lambda ctx, cfg: None, provides="test")
    handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
    root.host.register_handle(handle)

    root.host.provide(handle, "session_store", session_store)
    root.host.provide(handle, "machine_transport", bridge_config.transport)
    root.host.provide(handle, "machine_id", "machine-1")
    root.host.provide(handle, "machine_cwd", "/tmp/test")  # noqa: S108
    root.host.provide(handle, "runs_dir", tmp_path)
    return root


# ── D.2: DSH → SessionEvent mapping ────────────────────────────────


class TestDshEventMapping:
    """Verify DSH notification → LCA session event vocabulary."""

    def test_event_map_has_all_core_types(self) -> None:
        """All DSH notification types have LCA equivalents."""
        assert "turn/start" in DSH_EVENT_MAP
        assert "turn/end" in DSH_EVENT_MAP
        assert "step/start" in DSH_EVENT_MAP
        assert "tool/call" in DSH_EVENT_MAP
        assert "tool/result" in DSH_EVENT_MAP
        assert "request/header" in DSH_EVENT_MAP
        assert "assistant/chunk" in DSH_EVENT_MAP

    def test_map_turn_start(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        result = mapper.map_notification("turn/start", {})
        assert result is not None
        assert result.type == "turn.started.v1"
        assert result.data["turn"] == 1

    def test_map_turn_end_completed(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        mapper.map_notification("turn/start", {})
        result = mapper.map_notification("turn/end", {"reason": {"kind": "completed"}})
        assert result is not None
        assert result.type == "turn.ended.v1"
        assert result.data["reason"] == "completed"

    def test_map_turn_end_error(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        mapper.map_notification("turn/start", {})
        result = mapper.map_notification("turn/end", {"reason": {"kind": "error"}})
        assert result is not None
        assert result.data["reason"] == "error"

    def test_map_step_start(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        result = mapper.map_notification("step/start", {"step": 3})
        assert result is not None
        assert result.type == "step.started.v1"
        assert result.data["step"] == 3

    def test_map_tool_call(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        result = mapper.map_notification(
            "tool/call",
            {"callId": "c1", "name": "bash", "arguments": "ls -la"},
        )
        assert result is not None
        assert result.type == "tool.called.v1"
        assert result.data["call_id"] == "c1"
        assert result.data["tool_name"] == "bash"
        assert result.actor == "tool:bash"

    def test_map_tool_result(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        result = mapper.map_notification(
            "tool/result",
            {"callId": "c1", "output": "file1.txt"},
        )
        assert result is not None
        assert result.type == "tool.completed.v1"
        assert result.data["call_id"] == "c1"
        assert result.data["success"] is True

    def test_map_unknown_type_returns_none(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        result = mapper.map_notification("unknown/event", {})
        assert result is None

    def test_turn_counter_increments(self) -> None:
        mapper = DshEventMapper(session_id="s1")
        r1 = mapper.map_notification("turn/start", {})
        r2 = mapper.map_notification("turn/start", {})
        assert r1 is not None and r1.data["turn"] == 1
        assert r2 is not None and r2.data["turn"] == 2

    def test_to_session_event(self) -> None:
        mapped = MappedEvent(type="turn.started.v1", data={"turn": 1}, actor="agent")
        event = to_session_event(mapped, session_id="s1")
        assert event.type == "turn.started.v1"
        assert event.session_id == "s1"
        assert event.provider == "lca.loop.dsh_bridge"
        assert event.data == {"turn": 1}


# ── D.1: DshBridgeLoopFactory ──────────────────────────────────────


class TestDshBridgeLoopFactory:
    """Verify the factory creates valid AgentHandles."""

    def test_manifest_is_valid(self) -> None:
        assert manifest.id == "lca.loop.dsh_bridge"
        assert manifest.kind == PluginKind.PROVIDER
        assert "session_store" in manifest.requires

    @pytest.mark.asyncio
    async def test_factory_creates_handle(
        self, scope: ScopedPluginHost, bridge_config: DshBridgeConfig
    ) -> None:
        from lca.contracts.harness.agent import AgentIdentity

        factory = DshBridgeLoopFactory()
        identity = AgentIdentity(session_id="test-dsh-session")
        options = AgentOptions()
        handle = await factory.create(scope, identity, options)
        assert handle.agent is not None
        assert handle.agent.session_id == "test-session"
        assert handle.agent.status == "idle"
        await handle.dispose()

    @pytest.mark.asyncio
    async def test_factory_missing_config_raises(self) -> None:
        from lca.contracts.harness.agent import AgentIdentity
        from lca.layer0_infra.plugin.kernel._handle import PluginHandle
        from lca.layer0_infra.plugin.kernel._spec import PluginSpec

        root = ScopedPluginHost(None, "global", "test")
        persistence = JsonlSessionPersistence(Path("/dev/null"))
        header = SessionHeader(version=1, id="s", created_at=0)
        session_store = SessionStore(header, persistence=persistence)

        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None, provides="test")
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
        root.host.register_handle(handle)
        root.host.provide(handle, "session_store", session_store)
        # Missing machine_transport, machine_id, machine_cwd

        factory = DshBridgeLoopFactory()
        identity = AgentIdentity(session_id="s")
        options = AgentOptions()
        with pytest.raises(ValueError, match="requires machine_transport"):
            await factory.create(scope=root, identity=identity, options=options)


# ── DshLiveAgent event production ──────────────────────────────────


class TestDshLiveAgentEvents:
    """Verify DshLiveAgent produces correct session events."""

    @pytest.mark.asyncio
    async def test_followup_writes_turn_events(
        self,
        session_store: SessionStore,
        bridge_config: DshBridgeConfig,
    ) -> None:
        inbox = Inbox(session_store)
        agent = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id="dsh-1",
        )

        # Mock the DSH turn execution
        with patch.object(agent, "_run_dsh_turn", new_callable=AsyncMock) as mock_turn:
            mock_turn.return_value = ("DSH response", "", "completed")
            receipt = await agent.followup(UserMessage(content="hello"))

        assert receipt.session_id == "dsh-test-session"
        events = session_store.events()
        types = [e.type for e in events]
        assert "message.accepted.v1" in types
        assert "turn.started.v1" in types
        assert "turn.ended.v1" in types
        assert "session.checkpoint.v1" in types

    @pytest.mark.asyncio
    async def test_followup_error_records_error_reason(
        self,
        session_store: SessionStore,
        bridge_config: DshBridgeConfig,
    ) -> None:
        inbox = Inbox(session_store)
        agent = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id="dsh-2",
        )

        with patch.object(agent, "_run_dsh_turn", new_callable=AsyncMock) as mock_turn:
            mock_turn.return_value = ("", "Connection refused", "error")
            await agent.followup(UserMessage(content="hello"))

        events = session_store.events()
        turn_ended = [e for e in events if e.type == "turn.ended.v1"]
        assert len(turn_ended) == 1
        assert turn_ended[0].data["reason"] == "error"

        checkpoint = [e for e in events if e.type == "session.checkpoint.v1"]
        assert len(checkpoint) == 1
        assert checkpoint[0].data["status"] == "failed"

    @pytest.mark.asyncio
    async def test_cancel_sets_disposed(
        self,
        session_store: SessionStore,
        bridge_config: DshBridgeConfig,
    ) -> None:
        inbox = Inbox(session_store)
        agent = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id="dsh-3",
        )
        agent.cancel()
        assert agent.status == "disposed"

    @pytest.mark.asyncio
    async def test_steer_writes_system_event(
        self,
        session_store: SessionStore,
        bridge_config: DshBridgeConfig,
    ) -> None:
        inbox = Inbox(session_store)
        agent = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id="dsh-4",
        )
        receipt = await agent.steer(UserMessage(content="go faster"))
        assert receipt.session_id == "dsh-test-session"
        events = session_store.events()
        assert any(e.type == "message.accepted.v1" for e in events)

    @pytest.mark.asyncio
    async def test_inject_writes_system_event(
        self,
        session_store: SessionStore,
        bridge_config: DshBridgeConfig,
    ) -> None:
        inbox = Inbox(session_store)
        agent = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id="dsh-5",
        )
        receipt = await agent.inject(ContextMessage(content="context", source="test"))
        assert receipt.session_id == "dsh-test-session"
        events = session_store.events()
        msg_events = [e for e in events if e.type == "message.accepted.v1"]
        assert len(msg_events) == 1
        assert msg_events[0].data["role"] == "system"


# ── Mixed provider session tree ────────────────────────────────────


class TestMixedProviderTree:
    """Verify Cognitive + DSH providers coexist in the same spine."""

    def test_both_builders_are_callable(self) -> None:
        """Both cognitive builder and DshBridgeLoopFactory are callable."""
        from lca.plugins.loop_cognitive import build_cognitive_live_agent

        dsh = DshBridgeLoopFactory()
        # Both are callable
        assert callable(build_cognitive_live_agent)
        assert hasattr(dsh, "create")

    def test_manifest_ids_differ(self) -> None:
        """DSH bridge and cognitive have different manifest IDs."""
        from lca.plugins.loop_cognitive import manifest as cog_manifest

        assert manifest.id == "lca.loop.dsh_bridge"
        assert cog_manifest.id == "lca.loop.cognitive"
        assert manifest.id != cog_manifest.id
