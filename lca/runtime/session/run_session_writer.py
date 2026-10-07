"""Concrete RunSessionWriter (spec §B, ADR-0226 §1).

One writer per run. All append methods go through :meth:`SessionProtocol.append`
with the DSH-aligned surface event taxonomy
(``surface/user_message``, ``surface/assistant_message``, ``surface/tool_result``,
``log/tool_call``). Fail-loud on unbound Session — no silent ``None`` return,
no ContextVar lookup.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode

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
from lca.session.surface_types import DEVELOPER_MESSAGE_TYPE
from lca_kernel.events.fold.inputs import SURFACE_TOOL_RESULT_TYPE
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
    paths). A failed call's ``error`` must reach the model even when the
    content is non-empty — a source marker alone masked ``namespace_not_loaded``
    and reopened the retry loop (``run_f70ccf932e9d``: 24 ``send_message``
    re-asks). The journal keeps the fact split — payload in ``content``,
    classification in ``error`` — and this projection is the single place
    that joins them into what the model reads.
    """
    from lca.infrastructure.session.projections.tool_result_message import tool_error_text

    content = data.get("content")
    text = content if isinstance(content, str) else ("" if content is None else str(content))
    error_text = tool_error_text(data.get("error"))
    if error_text:
        return f"{text}\n{error_text}" if text.strip() else error_text
    if text.strip():
        return text
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
    if event.type in ("surface/tool_result", SURFACE_TOOL_RESULT_TYPE):
        msg = Message(
            role="tool",
            content=_tool_result_content(event.data),
            tool_call_id=event.data.get("tool_call_id"),
        )
        return msg
    if event.type == DEVELOPER_MESSAGE_TYPE:
        # ADR-0268 §6：cron handoff 作为 developer 消息注入父轮。
        return Message(role="developer", content=event.data.get("content"))
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

    def append_developer_message(
        self,
        *,
        message_id: str,
        content: str,
        job_id: str | None = None,
        run_id: str | None = None,
    ) -> EventRef:
        """Append a ``surface/developer_message`` row (ADR-0268 §6).

        Used by the cron handoff injection path: the worker report enters the
        parent session as a developer message before the next user turn, so
        the assistant can decide whether to surface it. ``job_id`` / ``run_id``
        stay in the journal for replay provenance.
        """
        session = self._require_session()
        event = session.append(
            DEVELOPER_MESSAGE_TYPE,
            {
                "message_id": message_id,
                "content": content,
                "job_id": job_id,
                "run_id": run_id,
            },
            surface_op="developer_message",
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
        # INV-CAP-04: Deterministic widget fallback guard when model omits widget
        if content is not None:
            pending = extract_pending_intents_from_events(session.snapshot_events())
            if pending:
                content = ensure_intent_widget_in_assistant_message(
                    raw_model_content=content,
                    pending_intents=pending,
                )
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
        # 局部导入:避免模块加载期引入 infrastructure 层依赖。
        from lca.infrastructure.session.projections.tool_result_message import (
            build_openai_tool_result_message,
        )

        session = self._require_session()
        assistant_seq = self._last_assistant_tool_call_seq(call_id)
        source_event_seqs = (assistant_seq,) if assistant_seq is not None else None
        event = session.append(
            SURFACE_TOOL_RESULT_TYPE,
            {
                "turn": turn,
                "step": step,
                "call_id": call_id,
                "content": content,
                "error": error,
                "meta": meta,
                "tool_call_id": call_id,
                # ADR-0201: derive_event_message 消费 data["message"] 构造
                # OpenAI tool 消息;缺失则工具结果无法进入模型可见面。
                "message": build_openai_tool_result_message(
                    tool_call_id=str(call_id),
                    content=content,
                    error=error,
                ),
            },
            # SurfaceOp 契约只允许 "append" | replace;"tool_result" 是
            # 事件类型后缀的误用,会导致 fold/投影静默丢弃本事件。
            surface_op="append",
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
        surface_events = [
            e
            for e in session.snapshot_events()
            if e.type.startswith("surface/") or e.type == SURFACE_TOOL_RESULT_TYPE
        ]
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


_CONNECTOR_WIDGET_RE = re.compile(r"\[widget:connector_auth\?([^\]]+)\]")


def _parse_connector_widget_qs(query: str) -> dict[str, str | None]:
    """Parse a ``[widget:connector_auth?...]`` query string into intent fields."""
    qs = parse_qs(query)
    return {
        "intent_id": (qs.get("intentId") or qs.get("intent_id") or [None])[0],
        "app_name": (qs.get("appName") or qs.get("app_name") or ["Connector"])[0],
        "connection_id": (qs.get("connectionId") or qs.get("connection_id") or [""])[0],
        "mode": (qs.get("mode") or [""])[0],
    }


def extract_pending_intents_from_events(
    events: Sequence[Any],
) -> list[dict[str, str]]:
    """Extract unmounted connector capability intents from session events (INV-CAP-04).

    An intent is considered unmounted if it was emitted in a ``surface/tool_result`` event
    but has not yet appeared in any preceding ``surface/assistant_message`` event.
    """
    mounted_intent_ids: set[str] = set()
    tool_intents: list[dict[str, str]] = []

    for event in events:
        event_type = getattr(event, "type", "")
        data = getattr(event, "data", {}) or {}

        if event_type == "surface/assistant_message":
            content = data.get("content") or ""
            for match in _CONNECTOR_WIDGET_RE.finditer(content):
                intent_id = _parse_connector_widget_qs(match.group(1))["intent_id"]
                if intent_id:
                    mounted_intent_ids.add(intent_id)

        elif event_type in ("surface/tool_result", SURFACE_TOOL_RESULT_TYPE):
            content = data.get("content") or ""
            found = False
            for match in _CONNECTOR_WIDGET_RE.finditer(content):
                fields = _parse_connector_widget_qs(match.group(1))
                intent_id = fields["intent_id"]
                if intent_id:
                    tool_intents.append(
                        {
                            "intent_id": intent_id,
                            "app_name": fields["app_name"],
                            "connection_id": fields["connection_id"],
                            "mode": fields["mode"],
                        }
                    )
                    found = True

            if not found:
                meta = data.get("meta") or {}
                intent_id = meta.get("intent_id") or data.get("intent_id")
                if intent_id:
                    tool_intents.append(
                        {
                            "intent_id": intent_id,
                            "app_name": meta.get("app_name") or data.get("app_name") or "Connector",
                            "connection_id": meta.get("connection_id") or data.get("connection_id") or "",
                            "mode": meta.get("mode") or data.get("mode") or "",
                        }
                    )

    # Return only unmounted intents (deduplicated by intent_id)
    seen: set[str] = set()
    unmounted: list[dict[str, str]] = []
    for item in tool_intents:
        iid = item["intent_id"]
        if iid not in mounted_intent_ids and iid not in seen:
            seen.add(iid)
            unmounted.append(item)

    return unmounted


def ensure_intent_widget_in_assistant_message(
    raw_model_content: str | None,
    pending_intents: Sequence[dict[str, Any] | Any] | None = None,
) -> str:
    """Ensure that all pending connector auth intents are represented as widgets (INV-CAP-04).

    If the raw model content already contains the intentId, it is not duplicated.
    Otherwise, a standard [widget:connector_auth?...] tag is appended.
    """
    content = raw_model_content or ""
    if not pending_intents:
        return content

    widgets_to_append: list[str] = []
    for item in pending_intents:
        if isinstance(item, dict):
            intent_id = item.get("intent_id") or item.get("intentId")
            app_name = item.get("app_name") or item.get("appName") or "Connector"
            connection_id = item.get("connection_id") or item.get("connectionId") or ""
            mode = item.get("mode") or ""
        else:
            intent_id = getattr(item, "intent_id", None) or getattr(item, "intentId", None)
            app_name = getattr(item, "app_name", "Connector") or getattr(item, "appName", "Connector")
            connection_id = getattr(item, "connection_id", "") or getattr(item, "connectionId", "")
            mode = getattr(item, "mode", "")

        if not intent_id:
            continue

        if intent_id in content:
            continue

        params: dict[str, str] = {
            "intentId": str(intent_id),
            "appName": str(app_name),
        }
        if connection_id:
            params["connectionId"] = str(connection_id)
        if mode:
            params["mode"] = str(mode)

        tag = f"[widget:connector_auth?{urlencode(params)}]"
        widgets_to_append.append(tag)

    if not widgets_to_append:
        return content

    suffix = "\n\n".join(widgets_to_append)
    if content.strip():
        return f"{content.rstrip()}\n\n{suffix}"
    return suffix


__all__ = [
    "RunSessionWriter",
    "SessionWriterUnboundError",
    "ensure_intent_widget_in_assistant_message",
    "extract_pending_intents_from_events",
]
