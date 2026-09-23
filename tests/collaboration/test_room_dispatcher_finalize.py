"""Tests for RoomDispatcher.finalize (room runtime go-live M1, Task 3)."""

import pytest

from lca.application.collaboration.room_dispatch import (
    RoomDispatcher,
    RoomNotFoundError,
    RunDispatchResult,
)
from lca.contracts.models.collaboration.peer import (
    PeerFoldedResult,
    RoomMessage,
    RoomMessageKind,
    RoomSpec,
)
from lca.domain.collaboration.room import RoomMessageStore


class _FakeRoomRepository:
    def __init__(self) -> None:
        self._rooms = {
            "room_1": RoomSpec(
                room_id="room_1",
                display_name="测试室",
                coordinator_agent_id="coordinator_sam",
                member_peer_ids=("arch_guanlan",),
                shared_topic_id="topic_1",
                routing_policy="coordinator_first",
            )
        }

    def get(self, room_id: str) -> RoomSpec | None:
        return self._rooms.get(room_id)


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


async def _noop_starter(*, objective: str, mode: str, correlation_id: str) -> RunDispatchResult:
    return RunDispatchResult(run_id="run_1", trace_id="trace_1", accepted=True)


def _folded() -> PeerFoldedResult:
    return PeerFoldedResult(
        task_id="task_1",
        member_findings={"arch_guanlan": "边界清晰"},
        synthesized_verdict="【协同汇报】全员共识已形成。",
        consensus_status="unanimous",
        member_metadata={"arch_guanlan": {"name": "观澜"}},
    )


@pytest.mark.asyncio
async def test_finalize_appends_folded_message():
    repo = _FakeRoomRepository()
    store = _FakeMessageStore()
    dispatcher = RoomDispatcher(repo, store, _noop_starter, clock=lambda: 2000.0)

    folded_msg = await dispatcher.finalize("room_1", "run_1", _folded())

    assert len(store.messages) == 1
    msg = store.messages[0]
    assert msg.kind == RoomMessageKind.FOLDED
    assert msg.sender_id == "coordinator_sam"
    assert msg.content == "【协同汇报】全员共识已形成。"
    assert msg.run_id == "run_1"
    assert msg.created_at_ms == 2000000

    assert folded_msg.payload["task_id"] == "task_1"
    assert folded_msg.payload["member_findings"] == {"arch_guanlan": "边界清晰"}
    assert folded_msg.payload["consensus_status"] == "unanimous"
    assert folded_msg.payload["member_metadata"] == {"arch_guanlan": {"name": "观澜"}}


@pytest.mark.asyncio
async def test_finalize_raises_for_unknown_room():
    repo = _FakeRoomRepository()
    store = _FakeMessageStore()
    dispatcher = RoomDispatcher(repo, store, _noop_starter)

    with pytest.raises(RoomNotFoundError, match="room not found: missing"):
        await dispatcher.finalize("missing", "run_1", _folded())
    assert store.messages == []
