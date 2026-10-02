"""Tests for the generic message reaction mechanism.

Covers MessageReaction validation, ReactionStore behavior, and
ReactToMessageTool execution.
"""

import pytest

from lca.contracts.models.messaging.reaction import MessageReaction
from lca.infrastructure.messaging.reaction_store import ReactionStore
from lca.infrastructure.tools.messaging.react_tool import ReactToMessageTool


# ── MessageReaction ──────────────────────────────────────────────


def test_reaction_accepts_single_emoji():
    r = MessageReaction(message_id="msg_1", emoji="🎉")
    assert r.message_id == "msg_1"
    assert r.emoji == "🎉"
    assert r.actor == "assistant"
    assert r.created_at is not None


def test_reaction_rejects_plain_text_emoji():
    with pytest.raises(Exception):
        MessageReaction(message_id="msg_1", emoji="hello")


def test_reaction_rejects_empty_emoji():
    with pytest.raises(Exception):
        MessageReaction(message_id="msg_1", emoji="   ")


def test_reaction_rejects_empty_message_id():
    with pytest.raises(Exception):
        MessageReaction(message_id="  ", emoji="👍")


def test_reaction_is_frozen():
    r = MessageReaction(message_id="msg_1", emoji="👍")
    with pytest.raises(Exception):
        r.emoji = "🎉"  # type: ignore[misc]


# ── ReactionStore ────────────────────────────────────────────────


def test_store_add_and_list():
    store = ReactionStore()
    store.add(MessageReaction(message_id="m1", emoji="👍"))
    items = store.list_for("m1")
    assert len(items) == 1
    assert items[0].emoji == "👍"


def test_store_multiple_reactions_on_same_message():
    store = ReactionStore()
    store.add(MessageReaction(message_id="m1", emoji="🎉"))
    store.add(MessageReaction(message_id="m1", emoji="👍"))
    items = store.list_for("m1")
    assert [i.emoji for i in items] == ["🎉", "👍"]


def test_store_isolated_by_message_id():
    store = ReactionStore()
    store.add(MessageReaction(message_id="m1", emoji="🎉"))
    store.add(MessageReaction(message_id="m2", emoji="❤️"))
    assert [i.emoji for i in store.list_for("m1")] == ["🎉"]
    assert [i.emoji for i in store.list_for("m2")] == ["❤️"]
    assert store.list_for("m3") == ()


def test_store_persist_and_reload(tmp_path):
    path = tmp_path / "reactions.json"
    store = ReactionStore(persist_path=path)
    store.add(MessageReaction(message_id="m1", emoji="🎉"))
    assert path.is_file()

    reloaded = ReactionStore(persist_path=path)
    items = reloaded.list_for("m1")
    assert len(items) == 1
    assert items[0].emoji == "🎉"


# ── ReactToMessageTool ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_react_tool_success():
    store = ReactionStore()
    tool = ReactToMessageTool(store=store)
    obs = await tool.execute({"message_id": "msg_42", "emoji": "👍"})
    assert obs.success is True
    assert obs.payload["message_id"] == "msg_42"
    assert obs.payload["emoji"] == "👍"
    assert len(store.list_for("msg_42")) == 1


@pytest.mark.asyncio
async def test_react_tool_rejects_invalid_emoji():
    tool = ReactToMessageTool(store=ReactionStore())
    obs = await tool.execute({"message_id": "msg_42", "emoji": "not-an-emoji"})
    assert obs.success is False
    assert obs.error is not None


@pytest.mark.asyncio
async def test_react_tool_rejects_missing_message_id():
    tool = ReactToMessageTool(store=ReactionStore())
    obs = await tool.execute({"message_id": "", "emoji": "🎉"})
    assert obs.success is False


def test_react_tool_metadata():
    assert ReactToMessageTool.name == "react_to_message"
    assert ReactToMessageTool.namespace == "agent"
    assert "message_id" in ReactToMessageTool.parameters["properties"]
    assert "emoji" in ReactToMessageTool.parameters["properties"]
    assert set(ReactToMessageTool.parameters["required"]) == {"message_id", "emoji"}
