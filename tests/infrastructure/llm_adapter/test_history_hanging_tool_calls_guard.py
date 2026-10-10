"""Tests for history hanging tool calls hygiene guard (INV-HISTORY-01).

Enforces OpenAI wire protocol compliance:
Whenever an assistant message emits tool_calls, every declared tool_call_id
must have a corresponding role='tool' message before subsequent turns or end-of-messages.
"""

from lca.infrastructure.llm_adapter.openai_compat.history._history import (
    openai_messages_with_history,
)


def test_openai_messages_with_history_keeps_fully_answered_calls_untouched() -> None:
    """Happy path: all tool calls are answered; messages remain unchanged."""
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
    msgs = openai_messages_with_history(system=None, prompt="summarize", history=history)

    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == "call_1"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "summarize"


def test_openai_messages_with_history_sanitizes_hanging_tool_calls() -> None:
    """INV-HISTORY-01: When assistant declares 3 tool calls and only 1 is answered,
    the missing 2 must be synthesized with role='tool' before the next user turn.
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
    msgs = openai_messages_with_history(system=None, prompt="proceed", history=history)

    # Expected: user -> assistant -> tool(call_1) -> tool(call_2, synthesized) -> tool(call_3, synthesized) -> user(proceed)
    assert len(msgs) == 6
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "tool" and msgs[2]["tool_call_id"] == "call_1"
    assert msgs[3]["role"] == "tool" and msgs[3]["tool_call_id"] == "call_2"
    assert msgs[4]["role"] == "tool" and msgs[4]["tool_call_id"] == "call_3"
    assert msgs[5]["role"] == "user" and msgs[5]["content"] == "proceed"


def test_openai_messages_with_history_sanitizes_consecutive_hanging_assistant_messages() -> None:
    """INV-HISTORY-01: When multiple assistant messages have hanging tool_calls
    (e.g. from previous run aborts or dropped execution), all must be healed.
    """
    history = [
        {"role": "user", "content": "turn 1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_old_1", "name": "tool1", "arguments": {}}],
        },
        # Missing tool message here! Immediately followed by another assistant turn:
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_old_2", "name": "tool2", "arguments": {}}],
        },
    ]
    msgs = openai_messages_with_history(system=None, prompt="", history=history)

    tool_call_ids_answered = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    assert "call_old_1" in tool_call_ids_answered
    assert "call_old_2" in tool_call_ids_answered

    # Verify every assistant with tool_calls is followed by its corresponding tool message
    for idx, msg in enumerate(msgs):
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            expected_ids = {c["id"] for c in msg["tool_calls"]}
            # Subsequent messages until next assistant or user must contain these ids
            subsequent_tool_ids = set()
            for nxt in msgs[idx + 1 :]:
                if nxt["role"] == "tool":
                    subsequent_tool_ids.add(nxt["tool_call_id"])
                else:
                    break
            assert expected_ids.issubset(subsequent_tool_ids), (
                f"Assistant message at {idx} tool calls {expected_ids} not answered before next turn"
            )
