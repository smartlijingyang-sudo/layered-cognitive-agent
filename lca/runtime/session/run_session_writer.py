"""Concrete RunSessionWriter (spec §B, ADR-0226 §1).

One writer per run. All append methods go through :meth:`SessionProtocol.append`
with the DSH-aligned surface event taxonomy
(``surface/user_message``, ``surface/assistant_message``, ``surface/tool_result``,
``log/tool_call``). Fail-loud on unbound Session — no silent ``None`` return,
no ContextVar lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from lca.contracts.models.core.conversation.conversation import ConversationTurn
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


def _tool_result_content(data: dict[str, Any]) -> str:
    """Render a tool result's model-visible text; never empty.

    An empty ``role=tool`` row is indistinguishable from an unanswered
    call, so the model re-issues it (``run_71456ce99914``: two sandbox
    timeouts came back zero-length and the model kept guessing file
    paths). The journal keeps the fact split — payload in ``content``,
    classification in ``error`` — and this projection is the single place
    that joins them into what the model reads.
    """
    content = data.get("content")
    text = content if isinstance(content, str) else ("" if content is None else str(content))
    if text.strip():
        return text
    error = data.get("error")
    if isinstance(error, dict):
        kind = error.get("kind") or "execution"
        message = str(error.get("message") or "").strip() or "unknown error"
        retryable = bool(error.get("retryable"))
        return f"[tool_error kind={kind} retryable={retryable}] {message}"
    return "[tool_result] (no output)"


def _surface_event_to_message(event: Any) -> Message:
    """Project a single surface event into the OpenAI message wire shape.

    Only ``surface/*`` events reach this point. Returns a single
    :class:`Message` per event; non-applicable keys are omitted.
    """
    if event.type == "surface/user_message":
        content = event.data.get("content") or ""
        return Message(role="user", content=content)
    if event.type == "surface/assistant_message":
        msg: Message = Message(role="assistant", content=event.data.get("content"))
        tool_calls = event.data.get("tool_calls")
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        return msg
    if event.type == "surface/tool_result":
        msg = Message(
            role="tool",
            content=_tool_result_content(event.data),
            tool_call_id=event.data.get("tool_call_id"),
        )
        return msg
    # Other surface event types (extensions) fall through with role=event.type
    # so orphan-drop and downstream consumers see them rather than silently drop.
    return Message(role=event.type)


def _drop_orphan_tool_results(
    messages: list[Message], counter: list[int] | None = None
) -> list[Message]:
    """Drop tool/result messages with ``tool_call_id`` not in any preceding assistant.

    Mirrors OpenAI's ``drop_orphan_function_calls``: a ``role=tool`` row is
    only valid if its ``tool_call_id`` was declared by an earlier
    ``role=assistant`` row's ``tool_calls`` list.

    ``counter`` (PR-2 G-17) is an optional 1-element list the caller can
    supply to observe how many orphans were dropped. Pre-PR-2 the count
    was 4/5 in a 5-``runCommand`` decision; post-PR-2 the count stays 0
    for any valid multi-call decision (the Body commits every declared
    call, so orphan-drop has no work to do). Wired through
    :meth:`RunSessionWriter.derive_messages` so the writer exposes
    ``orphan_dropped_count`` as a per-run metric for
    :class:`RunHealthReport`.
    """
    valid_call_ids: set[str] = set()
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict) and "id" in tc:
                    valid_call_ids.add(tc["id"])
    kept: list[Message] = []
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id") not in valid_call_ids:
            if counter is not None:
                counter[0] += 1
            continue
        kept.append(m)
    return kept


def _drop_reasoning_after_dropped_calls(messages: list[Message]) -> list[Message]:
    """Drop reasoning items emitted before a dropped tool call.

    No-op when no reasoning-item event type is in the journal: orphan-drop
    is conservative and only removes what it can identify. Returns the
    input unchanged.
    """
    return messages


class RunSessionWriter(RunSessionWriterProtocol):
    """Owner of the run-scoped Session. Single surface append path."""

    def __init__(self, *, session: SessionProtocol | None) -> None:
        self._session = session
        # PR-2 G-17: per-run counter incremented each time
        # ``_drop_orphan_tool_results`` removes a ``role=tool`` row whose
        # ``tool_call_id`` was not declared by any preceding assistant row.
        # Post-PR-2 this stays 0 for any well-formed multi-call decision
        # (Body commits every declared call before any tool runs).
        self._orphan_dropped_count: int = 0
        self._seeded_prior_turns: bool = False

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

    def seed_prior_turns(
        self,
        turns: Sequence[ConversationTurn],
    ) -> None:
        """Inject multi-turn conversation history into Session before the current task.

        Ensures C3 (facts traceable via Session single track) and ADR-0244.
        Idempotent: only seeds once per RunSessionWriter.
        """
        session = self._require_session()
        if self._seeded_prior_turns or not turns:
            return
        for idx, turn in enumerate(turns):
            if turn.role in ("user", "human"):
                session.append(
                    "surface/user_message",
                    {
                        "message_id": f"history:turn_{idx}",
                        "role": "user",
                        "content": turn.content,
                        "historical": True,
                    },
                    surface_op="user_message",
                )
            elif turn.role == "assistant":
                session.append(
                    "surface/assistant_message",
                    {
                        "turn": 0,
                        "step": 0,
                        "role": "assistant",
                        "content": turn.content,
                        "tool_calls": None,
                        "usage": None,
                        "historical": True,
                    },
                    surface_op="assistant_message",
                )
        self._seeded_prior_turns = True

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
        :func:`lca.nodes.think.history.assemble.history_assemble`
        will drop it before it reaches the model.
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
        """Walk the journal, surface events only, build the OpenAI messages list.

        Orphan-drop (OpenAI ``drop_orphan_function_calls`` mirror): drop
        tool/result messages whose ``tool_call_id`` is not present in any
        preceding assistant message. Drop reasoning items that follow a
        dropped call.

        PR-2 G-17: each call increments ``orphan_dropped_count`` for any
        ``role=tool`` row removed by orphan-drop. Read via the
        ``orphan_dropped_count`` property for the
        :class:`RunHealthReport` deriver.
        """
        session = self._require_session()
        surface_events = [e for e in session.snapshot_events() if e.type.startswith("surface/")]
        msgs = [_surface_event_to_message(e) for e in surface_events]
        counter: list[int] = [0]
        msgs = _drop_orphan_tool_results(msgs, counter=counter)
        self._orphan_dropped_count += counter[0]
        msgs = _drop_reasoning_after_dropped_calls(msgs)
        return msgs

    @property
    def orphan_dropped_count(self) -> int:
        """Lifetime count of orphan ``role=tool`` rows dropped at ``derive_messages``.

        PR-2 G-17 instrumentation: post-PR-2 this stays 0 for any
        well-formed multi-call decision because ``Body.dispatch_tool_calls``
        commits the assistant row (declaring every ``call_id``) BEFORE any
        tool runs, so orphan-drop never has work to do. Non-zero indicates
        the upstream seam regressed and the LLM feedback chain has been
        silently truncated.
        """
        return self._orphan_dropped_count

    def request_header(self) -> EpochHeader | None:
        """Return the folded :class:`EpochHeader` from the bound Session, if any.

        Per :class:`RunSessionWriterProtocol`, ``request_header`` is part of
        the Session contract; the writer calls it directly (no duck-type
        fallback). Sessions that have not yet folded a header return ``None``.
        """
        session = self._require_session()
        return session.request_header()


__all__ = ["RunSessionWriter", "SessionWriterUnboundError"]
