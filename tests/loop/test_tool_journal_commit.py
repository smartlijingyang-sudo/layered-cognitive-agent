"""ToolJournalReceipt commit tests (ADR-0194 P1-10)."""

from __future__ import annotations

from lca.contracts.harness.memory.events import (
    ToolCallResolvedCommitted,
    ToolDeniedCommitted,
    ToolInvokedCommitted,
)
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.observability.tool_journal_receipt import (
    ToolJournalReceipt,
    tool_call_resolved_receipt,
    tool_invoked_receipt,
    tool_started_receipt,
)
from lca.loop.tool_journal_commit import commit_tool_journal_receipt
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def test_commit_tool_journal_receipt_uses_fact_gateway() -> None:
    session = Session("t-tool-denied-1")
    token = set_publish_session(session)
    try:
        receipt = ToolJournalReceipt(
            catalog_event=ToolDeniedCommitted(tool_name="demo", reason="permission"),
            actor="body",
        )
        result = commit_tool_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "tool.denied.v1"
        assert event.actor == "body"
        assert event.data["tool_name"] == "demo"
        assert event.data["reason"] == "permission"
    finally:
        reset_publish_session(token)


def test_commit_tool_journal_receipt_noop_when_unbound() -> None:
    receipt = ToolJournalReceipt(
        catalog_event=ToolDeniedCommitted(tool_name="demo", reason="validation"),
        actor="body",
    )
    assert commit_tool_journal_receipt(receipt) is None


def test_commit_tool_call_resolved_receipt() -> None:
    session = Session("t-tool-resolved-1")
    token = set_publish_session(session)
    try:
        receipt = tool_call_resolved_receipt(
            tool_name="executeCode",
            tool_call_id="toolu_1",
            arguments={"code": "print(1)", "language": "python"},
        )
        result = commit_tool_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "tool.call.resolved.v1"
        assert event.actor == "brain"
        assert event.data["tool_name"] == "executeCode"
        assert event.data["tool_call_id"] == "toolu_1"
        assert event.data["arguments"]["code"] == "print(1)"
        committed = receipt.catalog_event
        assert isinstance(committed, ToolCallResolvedCommitted)
    finally:
        reset_publish_session(token)


def test_commit_tool_started_receipt() -> None:
    session = Session("t-tool-started-1")
    token = set_publish_session(session)
    try:
        receipt = tool_started_receipt(
            tool_name="read_file",
            invocation_id="inv-1",
            arguments={"path": "/workspace/x"},
        )
        result = commit_tool_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "tool.started.v1"
        assert event.actor == "body"
        assert event.data["tool_name"] == "read_file"
        assert event.data["invocation_id"] == "inv-1"
        assert event.data["arguments"] == {"path": "/workspace/x"}
        assert event.data["arguments_ref"] is None
    finally:
        reset_publish_session(token)


def test_commit_tool_invoked_receipt() -> None:
    session = Session("t-tool-invoked-1")
    token = set_publish_session(session)
    try:
        receipt = tool_invoked_receipt(
            tool_name="bash",
            invocation_id="inv-2",
            ok=True,
            latency_ms=42,
            attempt=1,
            output_text="hello",
            files=({"name": "out.txt", "mimeType": "text/plain"},),
        )
        result = commit_tool_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "tool.invoked.v1"
        assert event.data["ok"] is True
        assert event.data["latency_ms"] == 42
        assert event.data["output_text"] == "hello"
        assert event.data["files"][0]["name"] == "out.txt"
    finally:
        reset_publish_session(token)


def test_prepare_tool_invoked_from_observation() -> None:
    from lca.cognition.body.tool_journal_emit import prepare_tool_invoked

    class _Tool:
        name = "demo"

    obs = Observation(
        observation_id="o1",
        success=True,
        payload={"stdout": "done"},
        extra={"invocation_id": "inv-obs"},
    )
    receipt = prepare_tool_invoked(
        _Tool(),  # type: ignore[arg-type]
        {"q": 1},
        obs,
        latency_ms=5,
        attempt=1,
        invocation_id="inv-fallback",
    )
    committed = receipt.catalog_event
    assert isinstance(committed, ToolInvokedCommitted)
    assert committed.invocation_id == "inv-obs"
    assert committed.output_text == "done"
    assert committed.arguments == {"q": 1}
