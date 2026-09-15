"""Concrete RunSessionWriter (spec §B, ADR-0226 §1).

One writer per run. All append methods go through :meth:`SessionProtocol.append`
with the DSH-aligned surface event taxonomy
(``surface/user_message``, ``surface/assistant_message``, ``surface/tool_result``,
``log/tool_call``). Fail-loud on unbound Session — no silent ``None`` return,
no ContextVar lookup.
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.models.session.call_id import CallId
from lca.contracts.models.session.epoch_header import EpochHeader
from lca.contracts.models.session.event_ref import EventRef
from lca.contracts.models.session.message import Message
from lca.contracts.models.session.token_usage import TokenUsage
from lca.contracts.models.session.tool_call import ToolCall
from lca.contracts.models.session.tool_error import ToolError
from lca.contracts.protocols.session.run_session_writer import RunSessionWriterProtocol
from lca.session.lifecycle.bind import _event_ref_from_session
from lca_kernel.events.session.session import SessionEvent, SessionProtocol


class SessionWriterUnboundError(RuntimeError):
    """Raised when a RunSessionWriter method is called without a bound Session.

    Per ADR-0226 §1: writer methods fail loud — no silent ``None`` return and
    no ContextVar fallback. Construct the writer via
    :func:`lca.session.lifecycle.bind.bind_run_event_session_from_store`.
    """


class RunSessionWriter(RunSessionWriterProtocol):
    """Owner of the run-scoped Session. Single surface append path."""

    def __init__(self, *, session: SessionProtocol | None) -> None:
        self._session = session

    def _require_session(self) -> SessionProtocol:
        if self._session is None:
            raise SessionWriterUnboundError(
                "RunSessionWriter.append_* called without a bound Session. "
                "Construct the writer via bind_run_event_session_from_store."
            )
        return self._session

    @staticmethod
    def _event_ref(session: SessionProtocol, event: SessionEvent) -> EventRef:
        """Build an ``EventRef`` from a SessionEvent.

        Delegates to :func:`lca.session.lifecycle.bind._event_ref_from_session`
        so the writer and the bind observer share one canonical EventRef
        shape. Preserves ``event.time`` fidelity.
        """
        return _event_ref_from_session(session, event)

    def append_user_message(
        self,
        *,
        message_id: str,
        role: Literal["user", "human"],
        content: str,
    ) -> EventRef:
        session = self._require_session()
        event = session.append(
            "surface/user_message",
            {"message_id": message_id, "role": role, "content": content},
            surface_op="user_message",
        )
        return self._event_ref(session, event)

    def append_assistant_message(
        self,
        *,
        turn: int,
        step: int,
        role: Literal["assistant"],
        content: str | None,
        tool_calls: list[ToolCall] | None,
        usage: TokenUsage | None,
    ) -> EventRef:
        session = self._require_session()
        event = session.append(
            "surface/assistant_message",
            {
                "turn": turn,
                "step": step,
                "role": role,
                "content": content,
                "tool_calls": tool_calls,
                "usage": usage,
            },
            surface_op="assistant_message",
        )
        return self._event_ref(session, event)

    def append_tool_call(
        self,
        *,
        turn: int,
        step: int,
        call_id: CallId,
        name: str,
        arguments: str,
    ) -> EventRef:
        """Append a log-only pairing record (NOT a surface event).

        ``log/tool_call`` exists for replay fidelity and provenance; the
        Session fold derives messages by walking only surface events, so
        ``surface_op=None`` keeps this event out of the model-visible stream.
        """
        session = self._require_session()
        event = session.append(
            "log/tool_call",
            {
                "turn": turn,
                "step": step,
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            },
            surface_op=None,
        )
        return self._event_ref(session, event)

    def append_tool_result(
        self,
        *,
        turn: int,
        step: int,
        call_id: CallId,
        content: str,
        error: ToolError | None,
        meta: Any | None,
    ) -> EventRef:
        """Append a surface tool result and link it to the assistant row.

        The link uses ``source_event_seqs`` so the Session fold can pair this
        result with its preceding ``surface/assistant_message`` that declared
        the matching ``tool_call_id``.
        """
        session = self._require_session()
        assistant_seq = self._last_assistant_tool_call_seq(call_id)
        source_event_seqs = (assistant_seq,) if assistant_seq is not None else None
        event = session.append(
            "surface/tool_result",
            {
                "turn": turn,
                "step": step,
                "call_id": call_id,
                "content": content,
                "error": error,
                "meta": meta,
                "tool_call_id": call_id,
            },
            surface_op="tool_result",
            source_event_seqs=source_event_seqs,
        )
        return self._event_ref(session, event)

    def _last_assistant_tool_call_seq(self, call_id: CallId) -> int | None:
        """Locate the most recent surface/assistant_message seq that declared ``call_id``.

        Returns ``None`` when no preceding assistant row carried the matching
        tool call — in that case the result still appends, but orphan-drop at
        :func:`lca.cognition.think.history.assemble` (Task 2) will drop it
        before it reaches the model.
        """
        session = self._require_session()
        match_seq: int | None = None
        for event in session.snapshot_events():
            if event.type != "surface/assistant_message":
                continue
            tool_calls = event.data.get("tool_calls") or []
            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("id") == call_id:
                    match_seq = event.seq
                    break
            if match_seq is not None:
                break
        return match_seq

    def derive_messages(self) -> list[Message]:
        """Project surface events into the OpenAI-compatible message list.

        Implementation deferred to Task 2 (think.history.assemble). Marked
        xfail in tests until the orphan-drop step lands.
        """
        raise NotImplementedError("derive_messages is implemented in Task 2")

    def request_header(self) -> EpochHeader | None:
        """Return the folded :class:`EpochHeader` from the bound Session, if any.

        Per :class:`RunSessionWriterProtocol`, ``request_header`` is part of
        the Session contract; the writer calls it directly (no duck-type
        fallback). Sessions that have not yet folded a header return ``None``.
        """
        session = self._require_session()
        return session.request_header()


__all__ = ["RunSessionWriter", "SessionWriterUnboundError"]
