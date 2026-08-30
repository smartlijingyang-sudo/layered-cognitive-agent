"""Focused tests for the shared run terminalization module."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from gateway.runs.session.session import RunStatus
from gateway.runs.terminal.terminalizer import RunTerminalizer


def _session(*, canceled: bool = False) -> Any:
    session = MagicMock()
    session.run_id = "run-terminalizer"
    session.hub = None
    session.cancel_requested = canceled
    session.error = ""
    session.status = RunStatus.RUNNING
    session.closed_at = None
    return session


@pytest.mark.asyncio
async def test_terminalize_closes_then_materializes_and_cleans_registry() -> None:
    session = _session()
    registry = MagicMock()
    events: list[str] = []

    async def close_run(_run_id: str) -> None:
        events.append("close")

    def materialize(_session: Any) -> None:
        events.append("materialize")

    registry.clear_inflight.side_effect = lambda _run_id: events.append("clear")
    registry.prune.side_effect = lambda: events.append("prune")
    await RunTerminalizer(
        registry,
        finalizer=close_run,
        materializer=materialize,
    ).terminalize(session, workspace=None, success=True)

    assert session.status == RunStatus.COMPLETED
    assert events == ["close", "clear", "prune", "materialize"]


@pytest.mark.asyncio
async def test_missing_journal_finish_uses_failure_fallback() -> None:
    session = _session()
    session.hub = SimpleNamespace(
        journal=SimpleNamespace(store=SimpleNamespace(events=[])),
        close=lambda: None,
        flush=lambda: None,
    )
    registry = MagicMock()

    async def close_run(_run_id: str) -> None:
        return None

    await RunTerminalizer(
        registry,
        finalizer=close_run,
        materializer=lambda _session: None,
    ).terminalize(session, workspace=None, success=False)

    assert session.status == RunStatus.FAILED


@pytest.mark.asyncio
async def test_terminalize_preserves_cancel_signal_over_success() -> None:
    session = _session(canceled=True)
    registry = MagicMock()

    async def close_run(_run_id: str) -> None:
        return None

    await RunTerminalizer(
        registry,
        finalizer=close_run,
        materializer=lambda _session: None,
    ).terminalize(session, workspace=None, success=True)

    assert session.status == RunStatus.CANCELED
