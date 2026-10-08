"""RA-047: NativeToolCall rejects non-dict arguments at construction."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.conversation.llm import NativeToolCall


def test_string_arguments_raise_type_error_at_construction() -> None:
    """A JSON string passed as arguments must fail loud here — not later
    with an obscure error when the dict is actually used."""
    with pytest.raises(TypeError, match="must be dict"):
        NativeToolCall(call_id="c1", name="t", arguments='{"a": 1}')  # type: ignore[arg-type]


def test_dict_arguments_still_accepted() -> None:
    call = NativeToolCall(call_id="c1", name="t", arguments={"a": 1})
    assert call.arguments == {"a": 1}
