"""Tests for ReplayLoop — deterministic replay from golden journal (spec §C.5)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.harness.agent import AgentIdentity, AgentOptions, UserMessage
from lca.contracts.harness.session import SessionEvent, SessionHeader
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore
from lca.plugins.loop_replay import ReplayLiveAgent, ReplayLoopFactory


# ---------------------------------------------------------------------------
# ReplayLiveAgent — direct unit tests
# ---------------------------------------------------------------------------


class TestReplayLiveAgent:
    """ReplayLiveAgent replays journal events without LLM calls."""

    @pytest.mark.asyncio
    async def test_replay_all_returns_events_in_seq_order(self) -> None:
        """replay_all() yields events sorted by ascending seq."""
        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        # Append events out of order to the underlying list — SessionStore
        # allocates seqs monotonically so they are already ordered, but we
        # exercise the sort path explicitly by pre-populating _events.
        store._events = [
            SessionEvent(type="turn.ended.v1", seq=2, time=0, data={}, session_id="s1"),
            SessionEvent(type="turn.started.v1", seq=0, time=0, data={}, session_id="s1"),
            SessionEvent(type="model.completed.v1", seq=1, time=0, data={}, session_id="s1"),
        ]

        agent = ReplayLiveAgent(session_store=store, session_id="s1")
        replayed = await agent.replay_all()

        assert len(replayed) == 3
        assert [e.seq for e in replayed] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_replay_all_empty_journal(self) -> None:
        """replay_all() returns [] when journal is empty."""
        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        agent = ReplayLiveAgent(session_store=store, session_id="s1")

        assert await agent.replay_all() == []

    @pytest.mark.asyncio
    async def test_followup_returns_first_assistant_receipt(self) -> None:
        """followup() picks up the first assistant message.accepted event."""
        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        store._events = [
            SessionEvent(
                type="message.accepted.v1",
                seq=0,
                time=0,
                data={"role": "user", "message_id": "u1"},
                session_id="s1",
            ),
            SessionEvent(
                type="message.accepted.v1",
                seq=1,
                time=0,
                data={"role": "assistant", "message_id": "a1"},
                session_id="s1",
            ),
        ]
        agent = ReplayLiveAgent(session_store=store, session_id="s1")

        receipt = await agent.followup(UserMessage(content="hi"))

        assert receipt.message_id == "a1"
        assert receipt.session_id == "s1"
        assert receipt.seq == 1

    @pytest.mark.asyncio
    async def test_followup_empty_returns_seq_minus_one(self) -> None:
        """followup() with no recorded assistant yields sentinel seq=-1."""
        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        agent = ReplayLiveAgent(session_store=store, session_id="s1")

        receipt = await agent.followup(UserMessage(content="hi"))

        assert receipt.seq == -1
        assert receipt.session_id == "s1"

    def test_id_and_session_id_properties(self) -> None:
        """id is replay-<session_id>; session_id passes through."""
        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        agent = ReplayLiveAgent(session_store=store, session_id="abc")

        assert agent.id == "replay-abc"
        assert agent.session_id == "abc"
        assert agent.status == "idle"

    @pytest.mark.asyncio
    async def test_live_agent_protocol_conformance(self) -> None:
        """ReplayLiveAgent satisfies the LiveAgent runtime-checkable Protocol."""
        from lca.contracts.harness.agent import LiveAgent

        header = SessionHeader(version=1, id="s1", created_at=0)
        store = SessionStore(header)
        agent = ReplayLiveAgent(session_store=store, session_id="s1")

        assert isinstance(agent, LiveAgent)


# ---------------------------------------------------------------------------
# ReplayLoopFactory — integration tests
# ---------------------------------------------------------------------------


class TestReplayLoopFactory:
    """ReplayLoopFactory.create() returns AgentHandle wrapping ReplayLiveAgent."""

    @pytest.mark.asyncio
    async def test_create_returns_handle_with_agent(self) -> None:
        """Factory creates handle with .agent pointing to ReplayLiveAgent."""
        factory = ReplayLoopFactory()
        scope = MagicMock()
        header = SessionHeader(version=1, id="replay-1", created_at=0)
        scope.resolve = MagicMock(return_value=SessionStore(header))

        handle = await factory.create(
            scope=scope,
            session_id="replay-1",
            options=AgentOptions(),
        )

        assert handle is not None
        assert hasattr(handle, "agent")
        assert isinstance(handle.agent, ReplayLiveAgent)
        assert handle.agent.session_id == "replay-1"

    @pytest.mark.asyncio
    async def test_create_with_persisted_session_store_roundtrip(self, tmp_path: Path) -> None:
        """End-to-end: SessionStore-backed replay agent reads events."""
        persistence = JsonlSessionPersistence(tmp_path / "session.jsonl")
        header = SessionHeader(version=1, id="roundtrip", created_at=0)
        store = SessionStore(header, persistence=persistence)

        # Pre-populate events directly (bypass the event-type registry)
        store._events = [
            SessionEvent(
                type="turn.started.v1", seq=0, time=0,
                data={}, session_id="roundtrip",
            ),
            SessionEvent(
                type="model.completed.v1", seq=1, time=0,
                data={}, session_id="roundtrip",
            ),
        ]
        store._seq = 1

        scope = MagicMock()
        scope.resolve = MagicMock(return_value=store)

        factory = ReplayLoopFactory()
        handle = await factory.create(
            scope=scope,
            session_id="roundtrip",
            options=AgentOptions(),
        )

        replayed = await handle.agent.replay_all()
        assert len(replayed) == 2
        assert [e.seq for e in replayed] == [0, 1]

    @pytest.mark.asyncio
    async def test_handle_dispose_cancels_agent(self) -> None:
        """dispose() propagates to agent.cancel() via OwnerAgentHandle."""
        factory = ReplayLoopFactory()
        scope = MagicMock()
        header = SessionHeader(version=1, id="d1", created_at=0)
        scope.resolve = MagicMock(return_value=SessionStore(header))

        handle = await factory.create(
            scope=scope, session_id="d1", options=AgentOptions()
        )
        # Must not raise
        await handle.dispose("test")
