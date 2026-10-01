"""ModelVisibleHookAdapter wire message merge (ADR-0201 P2)."""

from __future__ import annotations

from lca.plugins.events.hooks.model_visible.adapter import _kwargs_for_hook


class _InnerLLM:
    name = "inner"


def test_kwargs_for_hook_merges_prompt_history_and_tool_role() -> None:
    history = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_1", "name": "executeCode", "arguments": {"code": "1"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "pdf text chunk"},
    ]
    out = _kwargs_for_hook(
        {"history": history},
        inner=_InnerLLM(),
        prompt="分析下这个文件",
    )
    messages = out["messages"]
    roles = [msg["role"] for msg in messages]
    # Spec §G: history precedes the new user turn; prompt lands last.
    assert roles == ["assistant", "tool", "user"]
    assert messages[-1]["content"] == "分析下这个文件"
    assert messages[1]["content"] == "pdf text chunk"


def test_kwargs_for_hook_records_the_first_turn_user_message() -> None:
    """An empty history must not record an empty request.

    The first turn of a run derives no history yet — the whole request is
    the prompt — and the header used to record ``messages: []``, so the
    SSOT for "what the model saw" could not answer what turn 1 asked.
    """
    out = _kwargs_for_hook(
        {"history": []},
        inner=_InnerLLM(),
        prompt="分析并输出pdf版本报告",
    )

    assert out["messages"] == ({"role": "user", "content": "分析并输出pdf版本报告"},)


def test_kwargs_for_hook_records_history_verbatim_when_prompt_is_empty() -> None:
    """``think.llm.invoke`` sends a complete message list with no extra user turn.

    A trailing ``role=tool`` row must survive into the record with its
    ``tool_call_id``; re-rendering it as a user turn is what left an
    assistant's ``tool_calls`` unanswered on the wire.
    """
    history = [
        {"role": "user", "content": "读一下附件"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "name": "executeCode", "arguments": {"code": "1"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "sheet contents"},
    ]

    out = _kwargs_for_hook({"history": history}, inner=_InnerLLM(), prompt="")

    assert out["messages"] == tuple(history)
    assert out["messages"][-1]["role"] == "tool"
    assert out["messages"][-1]["tool_call_id"] == "call_1"


def test_tool_calls_payload_uses_native_tool_call_name() -> None:
    """Regression: _tool_calls_payload read "tool_name" (an LLMStreamEvent
    field) instead of "name" (the NativeToolCall field), so the post-hook
    journal event recorded every tool call with an empty name."""
    from lca.contracts.models.core.conversation.llm import (
        LLMResponse,
        NativeToolCall,
    )
    from lca.plugins.events.hooks.model_visible.adapter import _tool_calls_payload

    response = LLMResponse(
        text="",
        tool_calls=[
            NativeToolCall(call_id="call_1", name="executeCode", arguments={"code": "1"}),
        ],
    )
    payload = _tool_calls_payload(response)
    assert payload is not None
    assert payload[0]["id"] == "call_1"
    assert payload[0]["name"] == "executeCode"
    assert payload[0]["arguments"] == '{"code": "1"}'


def test_tool_calls_payload_returns_none_without_tool_calls() -> None:
    from lca.contracts.models.core.conversation.llm import LLMResponse
    from lca.plugins.events.hooks.model_visible.adapter import _tool_calls_payload

    assert _tool_calls_payload(LLMResponse(text="ok")) is None
