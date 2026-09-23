"""Tests for JsonRoomMessageStore (room runtime go-live M1, Task 2)."""

from pathlib import Path

from lca.contracts.models.collaboration.peer import RoomMessage, RoomMessageKind
from lca.domain.collaboration.room import JsonRoomMessageStore


def _message(
    message_id: str, *, room_id: str = "room_1", content: str = "hi", created_at_ms: int = 1000
):
    return RoomMessage(
        message_id=message_id,
        room_id=room_id,
        kind=RoomMessageKind.USER,
        sender_id="user",
        content=content,
        created_at_ms=created_at_ms,
    )


def test_append_and_list_in_time_order(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    store.append(_message("m1", created_at_ms=1000, content="first"))
    store.append(_message("m2", created_at_ms=2000, content="second"))
    store.append(_message("m3", created_at_ms=1500, content="middle"))

    messages = store.list_messages("room_1")
    assert [m.message_id for m in messages] == ["m1", "m3", "m2"]
    assert messages[0].content == "first"


def test_append_is_idempotent_by_message_id(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    msg = _message("m1", content="hello")
    store.append(msg)
    store.append(msg)
    store.append(_message("m1", content="hello"))

    messages = store.list_messages("room_1")
    assert len(messages) == 1
    assert messages[0].content == "hello"


def test_list_unknown_room_returns_empty(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    assert store.list_messages("no_such_room") == ()


def test_get_returns_message_or_none(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    store.append(_message("m1"))
    assert store.get("room_1", "m1") is not None
    assert store.get("room_1", "m1").content == "hi"  # type: ignore[union-attr]
    assert store.get("room_1", "missing") is None


def test_jsonl_persistence_on_disk(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    store.append(_message("m1", content="persisted"))
    store.append(_message("m2", content="again"))

    lines = (
        (tmp_path / "rooms" / "room_1" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 2

    # A fresh store instance reads the same messages back.
    reloaded = JsonRoomMessageStore(base_dir=tmp_path)
    messages = reloaded.list_messages("room_1")
    assert [m.message_id for m in messages] == ["m1", "m2"]


def test_append_skips_existing_across_reload(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    store.append(_message("m1"))
    store.append(_message("m2"))

    reloaded = JsonRoomMessageStore(base_dir=tmp_path)
    reloaded.append(_message("m1", content="duplicate"))

    assert len(reloaded.list_messages("room_1")) == 2


def test_rooms_are_isolated_by_room_id(tmp_path: Path):
    store = JsonRoomMessageStore(base_dir=tmp_path)
    store.append(_message("m1", room_id="room_a", content="a"))
    store.append(_message("m1", room_id="room_b", content="b"))

    assert len(store.list_messages("room_a")) == 1
    assert len(store.list_messages("room_b")) == 1
    assert store.list_messages("room_a")[0].content == "a"
    assert store.list_messages("room_b")[0].content == "b"
