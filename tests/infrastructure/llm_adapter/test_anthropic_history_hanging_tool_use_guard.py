"""Tests for Anthropic history hanging tool_use hygiene guard (RA-117).

Enforces Anthropic wire protocol compliance, mirroring the OpenAI guard
(``test_history_hanging_tool_calls_guard.py`` / 8d1fe6f44):
whenever an assistant message emits ``tool_use`` blocks, every declared id
must have a corresponding ``tool_result`` block before subsequent turns or
end-of-messages — Anthropic rejects unanswered tool_use as a 400.

RA-117 documented choice: unanswered ids get SYNTHESIZED ``tool_result``
blocks (same "[system: tool execution not completed in session]" marker as
the OpenAI path) rather than dropping the hanging ``tool_use``.
"""

from typing import Any

from lca.infrastructure.llm_adapter.openai_compat.history._history import (
    anthropic_messages_with_history,
)


def _tool_use_ids(msg: dict[str, Any]) -> list[str]:
    return [
        b["id"]
        for b in msg.get("content") or []
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]


def _tool_result_ids(msg: dict[str, Any]) -> list[str]:
    return [
        b["tool_use_id"]
        for b in msg.get("content") or []
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]


def test_anthropic_messages_with_history_keeps_fully_answered_tool_use_untouched() -> None:
    """Happy path: all tool_use blocks are answered; messages remain unchanged."""
    history = [
        {"role": "user", "content": "search news"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "search", "arguments": {"q": "news"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "news results"},
    ]
    msgs = anthropic_messages_with_history(system=None, prompt="summarize", history=history)

    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert _tool_use_ids(msgs[1]) == ["call_1"]
    assert msgs[2]["role"] == "user"
    assert _tool_result_ids(msgs[2]) == ["call_1"]
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "summarize"


def test_anthropic_messages_with_history_synthesizes_hanging_tool_use() -> None:
    """RA-117: assistant declares 3 tool_use, 1 answered → 2 synthesized.

    The hanging tool_use blocks are preserved (not dropped); the missing
    tool_result blocks are synthesized with the same marker text as the
    OpenAI path.
    """
    history = [
        {"role": "user", "content": "search parallel"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "search", "arguments": {"q": "a"}},
                {"id": "call_2", "name": "search", "arguments": {"q": "b"}},
                {"id": "call_3", "name": "search", "arguments": {"q": "c"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result a"},
    ]
    msgs = anthropic_messages_with_history(system=None, prompt="proceed", history=history)

    # user -> assistant -> user(tool_result call_1) -> user(synth call_2)
    #   -> user(synth call_3) -> user("proceed")
    assert len(msgs) == 6
    assert msgs[1]["role"] == "assistant"
    assert _tool_use_ids(msgs[1]) == ["call_1", "call_2", "call_3"]
    assert _tool_result_ids(msgs[2]) == ["call_1"]
    assert _tool_result_ids(msgs[3]) == ["call_2"]
    assert _tool_result_ids(msgs[4]) == ["call_3"]
    for synth in (msgs[3], msgs[4]):
        assert "[system: tool execution not completed in session]" in synth["content"][0]["content"]
    assert msgs[5]["role"] == "user" and msgs[5]["content"] == "proceed"


def test_anthropic_messages_with_history_closes_hanging_tool_use_before_user_text() -> None:
    """RA-117: a user text message after a hanging tool_use triggers closure.

    The synthetic tool_result is inserted before the user text turn so the
    wire shape stays a valid Anthropic conversation.
    """
    history = [
        {"role": "user", "content": "turn 1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_x", "name": "tool1", "arguments": {}}],
        },
        # No tool result — a user text turn follows instead.
        {"role": "user", "content": "never mind, do something else"},
    ]
    msgs = anthropic_messages_with_history(system=None, prompt="", history=history)

    # user -> assistant -> user(synth tool_result call_x) -> user("never mind...")
    assert len(msgs) == 4
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user"
    assert _tool_result_ids(msgs[2]) == ["call_x"]
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "never mind, do something else"


def test_anthropic_messages_with_history_heals_consecutive_hanging_assistant_messages() -> None:
    """RA-117: multiple assistant messages with hanging tool_use all get healed."""
    history = [
        {"role": "user", "content": "turn 1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_old_1", "name": "tool1", "arguments": {}}],
        },
        # Missing tool result here! Immediately followed by another assistant turn:
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_old_2", "name": "tool2", "arguments": {}}],
        },
    ]
    msgs = anthropic_messages_with_history(system=None, prompt="", history=history)

    answered = {
        b["tool_use_id"]
        for m in msgs
        if m["role"] == "user" and isinstance(m.get("content"), list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    }
    assert {"call_old_1", "call_old_2"}.issubset(answered)

    # Every assistant tool_use id is answered before the next assistant,
    # user text message, or end of list.
    for idx, msg in enumerate(msgs):
        if msg["role"] != "assistant":
            continue
        expected = set(_tool_use_ids(msg))
        if not expected:
            continue
        got: set[str] = set()
        for nxt in msgs[idx + 1 :]:
            if nxt["role"] == "user" and isinstance(nxt.get("content"), list):
                got.update(_tool_result_ids(nxt))
            else:
                break
        assert expected.issubset(got), (
            f"Assistant message at {idx} tool_use {expected} not answered before next turn"
        )
