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
- The final message in the result is ``{"role": "user", "content": prompt}``.
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
