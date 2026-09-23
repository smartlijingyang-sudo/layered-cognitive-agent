"""Regression tests for coordinator_agent_id and topic_id wiring in room runtime.

Verifies:
1. RoomDispatcher.dispatch forwards coordinator_agent_id and selected_peers to RunStarter;
2. routes_rooms._start_run binds the coordinator_agent_id into the RunRequest agent
   and registers the gateway run with the room's topic_id and coordinator agent_id;
3. Backward compatibility: RunStarter with older 3-argument signature remains supported.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.collaboration.room_dispatch import (
    RoomDispatcher,
    RunDispatchResult,
)
from lca.contracts.models.collaboration.peer import (
    RoomMessageKind,
    RoomSpec,
)
from lca.domain.collaboration.room import (
    JsonRoomMessageStore,
    JsonRoomRepository,
)


@pytest.mark.asyncio
async def test_room_dispatcher_propagates_coordinator_to_starter(tmp_path) -> None:
    repo = JsonRoomRepository(base_dir=tmp_path)
    store = JsonRoomMessageStore(base_dir=tmp_path)
    room = RoomSpec(
        room_id="room_arch_01",
        display_name="架构决策室",
        coordinator_agent_id="arch_lead",
        member_peer_ids=("guanlan", "hengyue", "jingchuan"),
        shared_topic_id="topic_arch_01",
        routing_policy="coordinator_first",
    )
    repo.save(room)

    captured_kwargs: dict[str, Any] = {}

    async def _mock_starter(
        *,
        objective: str,
        mode: str,
        correlation_id: str,
        coordinator_agent_id: str | None = None,
        selected_peers: tuple[str, ...] | None = None,
        room_id: str | None = None,
    ) -> RunDispatchResult:
        captured_kwargs["objective"] = objective
        captured_kwargs["mode"] = mode
        captured_kwargs["correlation_id"] = correlation_id
        captured_kwargs["coordinator_agent_id"] = coordinator_agent_id
        captured_kwargs["selected_peers"] = selected_peers
        captured_kwargs["room_id"] = room_id
        return RunDispatchResult(run_id="run_test_123", trace_id="trace_test_123", accepted=True)

    dispatcher = RoomDispatcher(
        room_repository=repo,
        message_store=store,
        run_starter=_mock_starter,
    )

    started_msg = await dispatcher.dispatch("room_arch_01", "请 @guanlan 审查边界契约")
    assert started_msg.kind == RoomMessageKind.RUN_STARTED
    assert started_msg.sender_id == "arch_lead"
    assert captured_kwargs["coordinator_agent_id"] == "arch_lead"
    assert captured_kwargs["selected_peers"] == ("guanlan",)
    assert captured_kwargs["room_id"] == "room_arch_01"


@pytest.mark.asyncio
async def test_room_dispatcher_backward_compatible_3_arg_starter(tmp_path) -> None:
    repo = JsonRoomRepository(base_dir=tmp_path)
    store = JsonRoomMessageStore(base_dir=tmp_path)
    room = RoomSpec(
        room_id="room_arch_02",
        display_name="经典房间",
        coordinator_agent_id="coordinator_solo",
        member_peer_ids=(),
        shared_topic_id="topic_arch_02",
    )
    repo.save(room)

    # 3-arg lambda (no coordinator_agent_id or selected_peers)
    async def _legacy_starter(*, objective: str, mode: str, correlation_id: str) -> RunDispatchResult:
        return RunDispatchResult(run_id="run_legacy", trace_id="trace_legacy", accepted=True)

    dispatcher = RoomDispatcher(
        room_repository=repo,
        message_store=store,
        run_starter=_legacy_starter,
    )

    started = await dispatcher.dispatch("room_arch_02", "普通任务")
    assert started.run_id == "run_legacy"


@pytest.mark.asyncio
async def test_routes_rooms_start_run_binds_coordinator_and_topic() -> None:
    from lca.plugins.transport.webserver.routes_3.routes_rooms import _start_run

    mock_request = MagicMock()
    mock_run_port = MagicMock()
    mock_receipt = MagicMock(accepted=True, run_id="run_routed_01", trace_id="trace_routed_01", rejection_reason=None)
    mock_run_port.create_and_dispatch = AsyncMock(return_value=mock_receipt)
    mock_request.app.state.run_port = mock_run_port
    mock_request.app.state.ctx = MagicMock()
    mock_request.app.state.file_store = MagicMock()

    # Track register_gateway_run call
    gateway_runs: list[dict[str, Any]] = []

    async def _fake_register_gateway_run(request, *, run_id, topic_id, agent_id, body):
        gateway_runs.append({
            "run_id": run_id,
            "topic_id": topic_id,
            "agent_id": agent_id,
            "body": body,
        })

    import lca.plugins.transport.webserver.routes_3.routes_rooms as rr
    orig_reg = rr.register_gateway_run
    rr.register_gateway_run = _fake_register_gateway_run
    try:
        res = await _start_run(
            mock_request,
            room_id="room_live_99",
            objective="系统重构分析",
            mode="team",
            correlation_id="corr_99",
            coordinator_agent_id="arch_lead",
            selected_peers=("guanlan", "hengyue"),
        )
    finally:
        rr.register_gateway_run = orig_reg

    assert res.accepted is True
    assert res.run_id == "run_routed_01"

    # Verify RunRequest agent
    created_req = mock_run_port.create_and_dispatch.call_args[0][0]
    assert created_req.agent.agent_id == "arch_lead"
    assert created_req.options["room_id"] == "room_live_99"
    assert created_req.options["selected_peers"] == ["guanlan", "hengyue"]

    # Verify Gateway registration
    assert len(gateway_runs) == 1
    assert gateway_runs[0]["topic_id"] == "room_live_99"
    assert gateway_runs[0]["agent_id"] == "arch_lead"
