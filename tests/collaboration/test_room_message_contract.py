"""Tests for RoomMessage contract (room runtime go-live M1, Task 1)."""

from enum import StrEnum

import pytest
from pydantic import ValidationError

from lca.contracts.models.collaboration.peer import RoomMessage, RoomMessageKind


def _message(**overrides):
    fields = {
        "message_id": "room_msg_001",
        "room_id": "room_1",
        "kind": RoomMessageKind.USER,
        "sender_id": "user",
        "content": "hello",
        "created_at_ms": 1000,
    }
    fields.update(overrides)
    return RoomMessage(**fields)


def test_room_message_kind_is_strenum():
    assert issubclass(RoomMessageKind, StrEnum)
    assert RoomMessageKind.USER.value == "user"
    assert RoomMessageKind.RUN_STARTED.value == "run_started"
    assert RoomMessageKind.PEER.value == "peer"
    assert RoomMessageKind.FOLDED.value == "folded"
    assert RoomMessageKind.APPROVAL.value == "approval"


def test_room_message_accepts_valid_message():
    msg = _message()
    assert msg.message_id == "room_msg_001"
    assert msg.room_id == "room_1"
    assert msg.kind == RoomMessageKind.USER
    assert msg.sender_id == "user"
    assert msg.content == "hello"
    assert msg.correlation_id == ""
    assert msg.run_id == ""
    assert msg.payload == {}
    assert msg.created_at_ms == 1000


def test_room_message_defaults_correlation_and_run_id():
    msg = _message()
    assert msg.correlation_id == ""
    assert msg.run_id == ""


def test_room_message_is_frozen():
    msg = _message()
    with pytest.raises(ValidationError):
        msg.content = "mutated"  # type: ignore[misc]


def test_room_message_extra_forbidden():
    with pytest.raises(ValidationError):
        _message(unexpected="boom")


def test_room_message_kind_accepts_string_value():
    msg = _message(kind="folded")
    assert msg.kind == RoomMessageKind.FOLDED


def test_room_message_payload_default_factory_isolated():
    msg_a = _message()
    msg_b = _message()
    assert msg_a.payload is not msg_b.payload
    msg_a.payload["x"] = 1
    assert msg_b.payload == {}
