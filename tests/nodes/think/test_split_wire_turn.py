"""Contract tests for ``lca.nodes.think.llm.invoke._split_wire_turn``.

The function splits the assembled message list onto the adapter seam
``(prompt, history)``. Only a *trailing* ``role=user`` row with non-blank
text content becomes the prompt; every other trailing row (assistant with
tool_calls, tool with tool_call_id, blank user, non-string content) stays
in history so the wire builder never strips identifiers the turn still
needs (see ADR-0265 wire order audit [1]->[7]->[8]->[9]).
"""

from lca.nodes.think.llm.invoke import _split_wire_turn


def test_trailing_user_text_becomes_prompt():
    rows = [
        {"role": "assistant", "content": "how can I help?"},
        {"role": "user", "content": "what time is it"},
    ]
    prompt, history = _split_wire_turn(rows)
    assert prompt == "what time is it"
    assert history == [{"role": "assistant", "content": "how can I help?"}]


def test_trailing_tool_row_stays_in_history_with_tool_call_id():
    # A trailing role=tool row must NOT be lifted to prompt: the wire
    # builder would render the prompt as a new user turn and strip its
    # tool_call_id, leaving the assistant's tool_calls unanswered.
    tool_row = {"role": "tool", "tool_call_id": "call_7", "content": "ok"}
    rows = [
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_7"}]},
        tool_row,
    ]
    prompt, history = _split_wire_turn(rows)
    assert prompt == ""
    assert history[-1] is tool_row
    assert history[-1]["tool_call_id"] == "call_7"


def test_trailing_assistant_row_stays_in_history():
    # A trailing role=assistant row (declared tool_calls) is never
    # dropped into the prompt.
    rows = [
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_9"}]},
    ]
    prompt, history = _split_wire_turn(rows)
    assert prompt == ""
    assert history == rows


def test_empty_messages():
    assert _split_wire_turn([]) == ("", [])


def test_none_messages():
    assert _split_wire_turn(None) == ("", [])


def test_whitespace_only_user_content_not_split():
    rows = [{"role": "user", "content": "   \n  "}]
    prompt, history = _split_wire_turn(rows)
    assert prompt == ""
    assert history == rows


def test_non_string_user_content_not_split():
    rows = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    prompt, history = _split_wire_turn(rows)
    assert prompt == ""
    assert history == rows


def test_only_trailing_row_is_candidate():
    # An earlier user row is never promoted when the trailing row is not
    # a splittable user message: history order is preserved verbatim.
    rows = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_3"}]},
        {"role": "tool", "tool_call_id": "call_3", "content": "answer"},
    ]
    prompt, history = _split_wire_turn(rows)
    assert prompt == ""
    assert history == rows
    assert history[0]["content"] == "first question"
