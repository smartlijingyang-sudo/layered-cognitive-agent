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
