"""Wire-contract tests for client→server WS message shapes.

Gap D regression: ``ToolResultMessage`` must accept ``idempotencyKey`` so
the back-end can read the field for replay dedup. See
``lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway``
(lines 330-335) — it reads ``msg.get("idempotencyKey", "")`` from the raw
frame. The base ``_WireBase`` configures ``extra="ignore"``, so a field
that is not declared on the model is silently stripped from parsed dicts
even though it travels in the wire bytes.

These tests pin the field declaration so the schema matches the back-end
reader and the front-end sender.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.transport.gateway_messages import ToolResultMessage


def test_tool_result_message_schema_accepts_idempotency_key() -> None:
    """ToolResultMessage wire schema must carry idempotencyKey — the back-end
    relies on it for replay dedup (see commands.py:resume_approval).

    Front-end sends this field; back-end reads it via msg.get('idempotencyKey', '').
    Without the field declared, Pydantic's extra='ignore' silently strips it.
    """
    msg = ToolResultMessage(
        type="tool_result",
        toolCallId="tc1",
        success=True,
        content="answer",
        idempotencyKey="idem-abc-123",
    )
    dumped = msg.model_dump()
    assert dumped["idempotencyKey"] == "idem-abc-123"


def test_tool_result_message_idempotency_key_is_optional() -> None:
    """Older clients may not send the field — must remain optional."""
    msg = ToolResultMessage(
        type="tool_result",
        toolCallId="tc1",
        success=True,
        content="answer",
    )
    dumped = msg.model_dump()
    # extra="ignore" strips None for the optional field — confirm absence.
    assert "idempotencyKey" not in dumped or dumped["idempotencyKey"] is None


def test_tool_result_message_rejects_non_string_idempotency_key() -> None:
    """A non-string idempotencyKey would corrupt dedup; must be rejected."""
    with pytest.raises(ValidationError):
        ToolResultMessage(
            type="tool_result",
            toolCallId="tc1",
            success=True,
            content="answer",
            idempotencyKey=12345,  # type: ignore[arg-type]
        )


def test_tool_result_message_roundtrip_json_preserves_idempotency_key() -> None:
    """JSON round-trip (the WS wire shape) must preserve idempotencyKey."""
    msg = ToolResultMessage(
        type="tool_result",
        toolCallId="tc1",
        success=True,
        content="answer",
        idempotencyKey="idem-xyz-789",
    )
    raw = msg.model_dump_json()
    reparsed = ToolResultMessage.model_validate_json(raw)
    assert reparsed.idempotencyKey == "idem-xyz-789"
