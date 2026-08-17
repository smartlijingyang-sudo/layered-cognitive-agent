"""Tests for LegacyApiAdapter — bridges /runs/* to /v1/sessions/*."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.plugins.gateway_starlette.legacy_adapter import LegacyApiAdapter


class TestLegacyApiAdapter:
    """Translates old /runs/* API to new command-based API."""

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_completed(self):
        """Waits until projection shows completed status."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"activity": {"status": "completed"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state("session-1", timeout_s=5)
        assert result.values["activity"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_failed(self):
        """Terminates on failed status."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"activity": {"status": "failed"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state("session-1", timeout_s=5)
        assert result.values["activity"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_canceled(self):
        """Terminates on canceled status."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"activity": {"status": "canceled"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state("session-1", timeout_s=5)
        assert result.values["activity"]["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_waiting_input(self):
        """Terminates immediately on waiting_input status."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"activity": {"status": "waiting_input"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state("session-1", timeout_s=5)
        assert result.values["activity"]["status"] == "waiting_input"
        # Should only poll once since waiting_input is terminal
        assert gw.get_snapshot.await_count == 1

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_timeout(self):
        """Returns current state on timeout."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"activity": {"status": "working"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state(
            "session-1", timeout_s=0.1, poll_interval_s=0.02
        )
        assert result.values["activity"]["status"] == "working"
        # Should have polled multiple times before timing out
        assert gw.get_snapshot.await_count >= 1

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_transitions_to_terminal(self):
        """Polls through non-terminal states until terminal reached."""
        gw = MagicMock()
        working = MagicMock()
        working.values = {"activity": {"status": "working"}}
        completed = MagicMock()
        completed.values = {"activity": {"status": "completed"}}

        gw.get_snapshot = AsyncMock(side_effect=[working, working, completed])

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state(
            "session-1", timeout_s=5, poll_interval_s=0.01
        )
        assert result.values["activity"]["status"] == "completed"
        assert gw.get_snapshot.await_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_missing_activity(self):
        """Handles missing activity key gracefully — keeps polling until timeout."""
        gw = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {}
        gw.get_snapshot = AsyncMock(return_value=snapshot)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state(
            "session-1", timeout_s=0.1, poll_interval_s=0.02
        )
        assert result.values == {}
