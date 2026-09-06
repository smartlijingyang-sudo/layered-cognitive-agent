"""Inbox followup session emit on /runs entry (PR8.E.1 / ADR-0195 P3-12).

Journal ``InboxFollowupCreated`` dual-write retired; session ``inbox.spliced.v1``
via ``emit_inbox_spliced`` is the single production path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


class TestInboxFollowupCreation:
    def test_record_inbox_followup_emits_session_only(self) -> None:
        """``_record_inbox_followup`` MUST call ``emit_inbox_spliced`` (no journal record)."""
        from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import (
            _record_inbox_followup,
        )

        session = SimpleNamespace(run_id="run-test")
        question = "hello world"
        with patch("lca.infrastructure.observability.meta_event_emit.emit_inbox_spliced") as emit_mock:
            emit_mock.return_value = None
            with patch(
                "lca.infrastructure.session.lifecycle_emit.resolve_run_session_writer",
                return_value=object(),
            ):
                _record_inbox_followup(session=session, question=question, mode="solo")

        emit_mock.assert_called_once()
        kwargs = emit_mock.call_args.kwargs
        assert kwargs["target"] == "next_turn"
        assert kwargs["op"] == "append"
        assert kwargs["message_ids"]
        assert kwargs["messages"][0]["content"] == question

    def test_inbox_splice_carries_question(self) -> None:
        """Session inbox splice MUST carry the question in messages."""
        from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import (
            _record_inbox_followup,
        )

        question = "帮我总结这份文档的关键点"
        session = SimpleNamespace(run_id="run-test2")
        with patch("lca.infrastructure.observability.meta_event_emit.emit_inbox_spliced") as emit_mock:
            emit_mock.return_value = None
            with patch(
                "lca.infrastructure.session.lifecycle_emit.resolve_run_session_writer",
                return_value=object(),
            ):
                _record_inbox_followup(session=session, question=question, mode="solo")

        messages = emit_mock.call_args.kwargs.get("messages") or ()
        assert messages
        assert messages[0]["content"] == question[:200]
