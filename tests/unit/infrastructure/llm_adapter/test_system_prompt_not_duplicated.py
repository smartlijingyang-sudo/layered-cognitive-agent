"""Spec §G: system prompt must NOT be duplicated as a user-role message.

The ``openai_messages_with_history(system, prompt, history)`` helper
projects a folded ``EpochHeader.system`` string into the model's wire
payload. Prior to this fix, ``system`` was injected as ``messages[0]``
with ``role=user`` (the same role as the actual user turn), which
caused models to treat the system prompt as a user instruction.

The contract under test:

- If ``system`` is provided, the first message in the result is
  ``{"role": "system", "content": system}``.
- If ``system`` is ``None``, no ``role=system`` message is emitted.
- A non-empty ``prompt`` becomes the final ``{"role": "user"}`` turn; an
  empty one adds nothing, so a caller whose message list is already
  complete keeps its trailing ``role=tool`` / ``role=assistant`` row intact.
"""

from __future__ import annotations

from lca.infrastructure.llm_adapter.openai_compat.history._history import (
    openai_messages_with_history,
)


def test_system_prompt_is_role_system_not_role_user() -> None:
    """System prompt must NOT appear as messages[0] role=user."""
    msgs = openai_messages_with_history(
        system="You are a helpful assistant.",
        prompt="hello",
        history=None,
    )
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a helpful assistant."
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "hello"


def test_no_system_prompt_no_system_role_message() -> None:
    msgs = openai_messages_with_history(system=None, prompt="hello", history=None)
    assert all(m["role"] != "system" for m in msgs)
    assert msgs == [{"role": "user", "content": "hello"}]


def test_empty_prompt_appends_no_user_turn() -> None:
    """An already-complete message list must not gain a trailing empty user row.

    ``think.llm.invoke`` passes the whole derived list as ``history`` with
    an empty prompt whenever the last row is not a user turn; appending
    ``{"role": "user", "content": ""}`` there would leave the preceding
    ``assistant.tool_calls`` without its ``role=tool`` reply.
    """
    history = [
        {"role": "user", "content": "read it"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "name": "runCommand", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "file contents"},
    ]
    msgs = openai_messages_with_history(system="sys", prompt="", history=history)

    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[-1] == {"role": "tool", "tool_call_id": "c1", "content": "file contents"}
    assert msgs[2]["tool_calls"][0]["id"] == "c1"


def test_assistant_text_survives_next_to_its_tool_calls() -> None:
    """The model's own narration is context; dropping it makes turns incoherent."""
    history = [
        {
            "role": "assistant",
            "content": "让我先激活技能。",
            "tool_calls": [
                {"id": "c1", "name": "activate_skill", "arguments": {"skill_id": "pdf"}}
            ],
        },
        {"role": "assistant", "content": "纯文本回复"},
    ]
    msgs = openai_messages_with_history(system=None, prompt="", history=history)

    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"] == "让我先激活技能。"
    assert msgs[0]["tool_calls"][0]["function"]["name"] == "activate_skill"
    assert msgs[1] == {"role": "assistant", "content": "纯文本回复"}


def test_anthropic_wire_keeps_tool_result_and_assistant_text() -> None:
    """The sibling Anthropic projection honors the same two rules."""
    from lca.infrastructure.llm_adapter.openai_compat.history._history import (
        anthropic_messages_with_history,
    )

    history = [
        {
            "role": "assistant",
            "content": "让我看看。",
            "tool_calls": [
                {"id": "c1", "name": "readFile", "arguments": {"path": "/mnt/data/a.xlsx"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "sheet contents"},
    ]
    msgs = anthropic_messages_with_history(system="sys", prompt="", history=history)

    assert [m["role"] for m in msgs] == ["system", "assistant", "user"]
    assert msgs[1]["content"][0] == {"type": "text", "text": "让我看看。"}
    assert msgs[1]["content"][1]["type"] == "tool_use"
    assert msgs[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "c1",
        "content": "sheet contents",
    }
