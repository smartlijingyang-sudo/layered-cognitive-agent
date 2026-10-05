"""Liveness filtering on GET /v1/topics/{topic_id}/running-op.

``lca_running_operations`` has no status column and its rows are never deleted,
so the latest row for a topic is usually a run that ended long ago. Without a
liveness check the endpoint answers with a dead run and every caller attaches to
a stream that will never emit.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    get_running_operation,
)
from tests.lca_plugins.transport.webserver.test_run_isolation import (
    FakeSession,
    _make_app_state,
    _make_http_request,
)

_ROW: dict[str, Any] = {"run_id": "run_1", "topic_id": "top_1", "agent_id": "solo"}


def _store_with(row: dict[str, Any] | None) -> Any:
    from unittest.mock import AsyncMock, MagicMock

    store = MagicMock()
    store.get_latest_for_topic = AsyncMock(return_value=row)
    return store


async def _call(session: Any, *, user: str = "user_owner", dev_mode: bool = True) -> Any:
    sessions = {} if session is None else {"run_1": session}
    app_state = _make_app_state(dev_mode=dev_mode, sessions=sessions)
    app_state.running_operation_store = _store_with(dict(_ROW))
    request = _make_http_request(
        "/v1/topics/top_1/running-op",
        headers={"x-lca-user-id": user},
        path_params={"topic_id": "top_1"},
        app_state=app_state,
    )
    response = await get_running_operation(request)
    assert response.status_code == 200
    return json.loads(response.body.decode())["running_operation"]


@pytest.mark.parametrize(
    "status",
    [
        RunLifecycleStatus.PENDING,
        RunLifecycleStatus.RUNNING,
        RunLifecycleStatus.PAUSED,
        RunLifecycleStatus.WAITING_INPUT,
    ],
)
@pytest.mark.asyncio
async def test_a_live_run_is_returned(status: RunLifecycleStatus) -> None:
    """PAUSED and WAITING_INPUT count as live: that run still owes an approval card."""
    session = FakeSession("run_1", user_id="user_owner")
    session.status = status

    assert await _call(session) == _ROW


@pytest.mark.parametrize(
    "status",
    [
        RunLifecycleStatus.COMPLETED,
        RunLifecycleStatus.FAILED,
        RunLifecycleStatus.CANCELLED,
        RunLifecycleStatus.TIMEOUT,
    ],
)
@pytest.mark.asyncio
async def test_a_terminal_run_is_not_returned(status: RunLifecycleStatus) -> None:
    session = FakeSession("run_1", user_id="user_owner")
    session.status = status

    assert await _call(session) is None


@pytest.mark.asyncio
async def test_a_run_the_registry_no_longer_holds_is_not_returned() -> None:
    """An empty registry after a restart reads as nothing live, which is true."""
    assert await _call(None) is None


@pytest.mark.asyncio
async def test_a_live_run_still_hides_from_another_tenant() -> None:
    """Ownership is a separate gate and must still bite once liveness passes."""
    session = FakeSession("run_1", user_id="user_owner")
    session.status = RunLifecycleStatus.RUNNING

    assert await _call(session, user="user_attacker", dev_mode=False) is None
    assert await _call(session, user="user_owner", dev_mode=False) == _ROW


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RunLifecycleStatus.PENDING, False),
        (RunLifecycleStatus.RUNNING, False),
        (RunLifecycleStatus.PAUSED, False),
        (RunLifecycleStatus.WAITING_INPUT, False),
        (RunLifecycleStatus.COMPLETED, True),
        (RunLifecycleStatus.FAILED, True),
        (RunLifecycleStatus.CANCELLED, True),
        (RunLifecycleStatus.TIMEOUT, True),
        (None, True),
        ("running", False),
        ("completed", True),
    ],
)
def test_is_terminal_covers_the_whole_vocabulary(
    status: RunLifecycleStatus | str | None, expected: bool
) -> None:
    assert RunLifecycleStatus.is_terminal(status) is expected
