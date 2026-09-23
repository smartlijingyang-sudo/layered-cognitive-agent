"""Tests for RoomDispatcher (room runtime go-live M1, Task 3)."""

import pytest

from lca.application.collaboration.room_dispatch import (
    RoomDispatcher,
    RoomNotFoundError,
    RunDispatchResult,
)
from lca.contracts.models.collaboration.peer import (
    RoomMessage,
    RoomMessageKind,
    RoomSpec,
)
from lca.domain.collaboration.room import RoomMessageStore


class _FakeRoomRepository:
    def __init__(self, rooms: dict[str, RoomSpec] | None = None) -> None:
        self._rooms = dict(rooms or {})

    def save(self, room: RoomSpec) -> None:
        self._rooms[room.room_id] = room

    def get(self, room_id: str) -> RoomSpec | None:
        return self._rooms.get(room_id)

    def list_rooms(self) -> tuple[RoomSpec, ...]:
        return tuple(self._rooms.values())

    def delete(self, room_id: str) -> bool:
        return self._rooms.pop(room_id, None) is not None


class _FakeMessageStore(RoomMessageStore):
    def __init__(self) -> None:
        self.messages: list[RoomMessage] = []

    def append(self, message: RoomMessage) -> None:
        self.messages.append(message)

    def list_messages(self, room_id: str) -> tuple[RoomMessage, ...]:
        return tuple(m for m in self.messages if m.room_id == room_id)

    def get(self, room_id: str, message_id: str) -> RoomMessage | None:
        for m in self.messages:
            if m.room_id == room_id and m.message_id == message_id:
                return m
        return None


class _RecordingRunStarter:
    def __init__(self, *, accepted: bool = True, rejection_reason: str | None = None) -> None:
        self.accepted = accepted
        self.rejection_reason = rejection_reason
        self.calls: list[dict[str, str]] = []
        self._counter = 0

    async def __call__(
        self, *, objective: str, mode: str, correlation_id: str
    ) -> RunDispatchResult:
        self.calls.append({"objective": objective, "mode": mode, "correlation_id": correlation_id})
        self._counter += 1
        return RunDispatchResult(
            run_id=f"run_{self._counter}",
            trace_id=f"trace_{self._counter}",
            accepted=self.accepted,
            rejection_reason=self.rejection_reason,
        )


def _room(room_id: str = "room_1", *, member_peer_ids=("arch_guanlan",)) -> RoomSpec:
    return RoomSpec(
        room_id=room_id,
        display_name="测试室",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=member_peer_ids,
        shared_topic_id="topic_1",
        routing_policy="coordinator_first",
    )


def _dispatcher(repo, store, starter) -> RoomDispatcher:
    return RoomDispatcher(repo, store, starter, clock=lambda: 1000.0)


@pytest.mark.asyncio
async def test_dispatch_appends_user_then_run_started():
    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    started = await dispatcher.dispatch("room_1", "请帮我梳理架构", sender_id="alice")

    kinds = [m.kind for m in store.messages]
    assert kinds == [RoomMessageKind.USER, RoomMessageKind.RUN_STARTED]

    user_msg = store.messages[0]
    assert user_msg.sender_id == "alice"
    assert user_msg.content == "请帮我梳理架构"
    assert user_msg.created_at_ms == 1000000

    assert started.kind == RoomMessageKind.RUN_STARTED
    assert started.sender_id == "coordinator_sam"
    assert started.content == "已启动 run run_1"
    assert started.run_id == "run_1"
    assert started.payload["trace_id"] == "trace_1"
    assert started.payload["accepted"] is True
    assert started.payload["rejection_reason"] is None
    assert started.created_at_ms == 1000000


@pytest.mark.asyncio
async def test_dispatch_raises_for_unknown_room():
    repo = _FakeRoomRepository()
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    with pytest.raises(RoomNotFoundError, match="room not found: missing"):
        await dispatcher.dispatch("missing", "hello")
    assert store.messages == []


@pytest.mark.asyncio
async def test_dispatch_mode_team_when_members_exist():
    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    await dispatcher.dispatch("room_1", "hello")
    assert starter.calls[0]["mode"] == "team"


@pytest.mark.asyncio
async def test_dispatch_mode_solo_when_no_members():
    room = _room(member_peer_ids=())
    repo = _FakeRoomRepository({room.room_id: room})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    await dispatcher.dispatch("room_1", "hello")
    assert starter.calls[0]["mode"] == "solo"


@pytest.mark.asyncio
async def test_dispatch_correlation_id_flows_to_starter_and_message():
    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    started = await dispatcher.dispatch("room_1", "hello")
    correlation_id = starter.calls[0]["correlation_id"]
    assert correlation_id.startswith("room_")
    assert started.correlation_id == correlation_id


@pytest.mark.asyncio
async def test_dispatch_selected_peers_recorded_in_payload():
    room = _room()
    repo = _FakeRoomRepository({room.room_id: room})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)

    started = await dispatcher.dispatch("room_1", "@arch_guanlan 请核查")
    assert started.payload["selected_peers"] == ["arch_guanlan"]


@pytest.mark.asyncio
async def test_dispatch_preserves_user_message_when_run_rejected():
    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter(accepted=False, rejection_reason="no llm key")
    dispatcher = _dispatcher(repo, store, starter)

    started = await dispatcher.dispatch("room_1", "hello")
    assert started.payload["accepted"] is False
    assert started.payload["rejection_reason"] == "no llm key"
    assert store.messages[0].kind == RoomMessageKind.USER


class _FakeRunStatusReader:
    def __init__(self, outcome) -> None:
        self.outcome = outcome

    async def __call__(self, run_id: str):
        del run_id
        return self.outcome


def _dispatcher_with_status(repo, store, starter, status_reader) -> RoomDispatcher:
    return RoomDispatcher(
        repo,
        store,
        starter,
        clock=lambda: 1000.0,
        run_status_reader=status_reader,
    )


async def _dispatch_and_start(repo, store, starter, dispatcher) -> RoomMessage:
    return await dispatcher.dispatch("room_1", "hello")


@pytest.mark.asyncio
async def test_sync_completed_appends_folded_for_completed_run():
    from lca.application.collaboration.room_dispatch import RunOutcome

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher_with_status(
        repo, store, starter, _FakeRunStatusReader(RunOutcome(status="completed"))
    )
    started = await dispatcher.dispatch("room_1", "hello")

    appended = await dispatcher.sync_completed("room_1")

    assert len(appended) == 1
    folded = appended[0]
    assert folded.kind == RoomMessageKind.FOLDED
    assert folded.correlation_id == started.correlation_id
    assert folded.run_id == started.run_id
    assert folded.payload["consensus_status"] == "unanimous"
    assert "已完成" in folded.content


@pytest.mark.asyncio
async def test_sync_completed_uses_full_output_as_verdict():
    from lca.application.collaboration.room_dispatch import RunOutcome

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher_with_status(
        repo,
        store,
        starter,
        _FakeRunStatusReader(RunOutcome(status="completed", output="完整结论文本")),
    )
    await dispatcher.dispatch("room_1", "hello")

    appended = await dispatcher.sync_completed("room_1")

    assert len(appended) == 1
    folded = appended[0]
    assert folded.kind == RoomMessageKind.FOLDED
    assert folded.content == "完整结论文本"
    assert folded.payload["consensus_status"] == "unanimous"


@pytest.mark.asyncio
async def test_sync_completed_is_idempotent():
    from lca.application.collaboration.room_dispatch import RunOutcome

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher_with_status(
        repo, store, starter, _FakeRunStatusReader(RunOutcome(status="completed"))
    )
    await dispatcher.dispatch("room_1", "hello")

    first = await dispatcher.sync_completed("room_1")
    second = await dispatcher.sync_completed("room_1")

    assert len(first) == 1
    assert len(second) == 0
    assert sum(1 for m in store.messages if m.kind == RoomMessageKind.FOLDED) == 1


@pytest.mark.asyncio
async def test_sync_completed_skips_inflight_run():
    from lca.application.collaboration.room_dispatch import RunOutcome

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher_with_status(
        repo, store, starter, _FakeRunStatusReader(RunOutcome(status="running"))
    )
    await dispatcher.dispatch("room_1", "hello")

    appended = await dispatcher.sync_completed("room_1")

    assert appended == ()
    assert all(m.kind != RoomMessageKind.FOLDED for m in store.messages)


@pytest.mark.asyncio
async def test_sync_completed_failed_run_uses_concerns_noted():
    from lca.application.collaboration.room_dispatch import RunOutcome

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher_with_status(
        repo,
        store,
        starter,
        _FakeRunStatusReader(RunOutcome(status="failed", error="boom")),
    )
    started = await dispatcher.dispatch("room_1", "hello")

    appended = await dispatcher.sync_completed("room_1")

    assert len(appended) == 1
    folded = appended[0]
    assert folded.payload["consensus_status"] == "concerns_noted"
    assert "boom" in folded.content
    assert folded.correlation_id == started.correlation_id


@pytest.mark.asyncio
async def test_finalize_sets_correlation_id_from_run_started():
    from lca.contracts.models.collaboration.peer import PeerFoldedResult

    repo = _FakeRoomRepository({_room().room_id: _room()})
    store = _FakeMessageStore()
    starter = _RecordingRunStarter()
    dispatcher = _dispatcher(repo, store, starter)
    started = await dispatcher.dispatch("room_1", "hello")

    folded = PeerFoldedResult(
        task_id=started.correlation_id,
        synthesized_verdict="结论",
        member_findings={},
        consensus_status="unanimous",
        member_metadata={},
    )
    msg = await dispatcher.finalize("room_1", started.run_id, folded)

    assert msg.kind == RoomMessageKind.FOLDED
    assert msg.correlation_id == started.correlation_id
