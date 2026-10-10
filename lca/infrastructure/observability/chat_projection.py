"""Durable chat rows for one LCA run.

The messages table is what a refresh renders. The Redis stream is only the
live accelerator, and it is deleted when the run ends. The row ids are a
pure function of ``run_id`` so a retry, a second pause, and a refresh all
land on the same rows.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

_log = structlog.get_logger(__name__)

_ASK_API = "askUserQuestion"
_ASK_IDENTIFIER = "lobe-user-interaction"


@dataclass(frozen=True)
class ChatIdentity:
    """The four fields a LobeHub message row cannot exist without."""

    run_id: str
    user_id: str
    topic_id: str
    agent_id: str


def final_message_id(run_id: str) -> str:
    return f"lca-final-{run_id}"


def ask_message_id(run_id: str) -> str:
    return f"lca-ask-{run_id}"


def identity_from_session(session: Any) -> ChatIdentity | None:
    """Read the projection key off a run session.

    ``user_id`` and the Lobe agent id are often absent on the session
    (the principal is ``solo``). The topic's existing message row fills
    those in at write time. A run with no topic cannot be projected.
    """
    run_id = str(getattr(session, "run_id", "") or "")
    topic_id = str(getattr(session, "topic_id", "") or "")
    if not (run_id and topic_id):
        return None
    agent = getattr(session, "agent", None)
    agent_id = str(getattr(session, "agent_id", "") or getattr(agent, "agent_id", "") or "")
    return ChatIdentity(
        run_id=run_id,
        user_id=str(getattr(session, "user_id", "") or ""),
        topic_id=topic_id,
        agent_id=agent_id,
    )


def resolve_identity(cur: Any, identity: ChatIdentity) -> ChatIdentity | None:
    """Fill user and agent from the topic when the session only knows ``solo``."""
    user_id = identity.user_id
    agent_id = identity.agent_id
    if not user_id or not agent_id or agent_id == "solo":
        cur.execute(
            """
            SELECT user_id, agent_id FROM messages
            WHERE topic_id = %s AND user_id IS NOT NULL AND agent_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (identity.topic_id,),
        )
        row = cur.fetchone()
        if row:
            user_id = user_id or str(row[0] or "")
            if not agent_id or agent_id == "solo":
                agent_id = str(row[1] or "")
    if not (user_id and agent_id):
        return None
    return ChatIdentity(
        run_id=identity.run_id,
        user_id=user_id,
        topic_id=identity.topic_id,
        agent_id=agent_id,
    )


def pending_question(approval_request: Any) -> tuple[str, list[Any]] | None:
    """Return ``(tool_call_id, questions)`` when the pause is a real question."""
    if not isinstance(approval_request, dict):
        return None
    questions = approval_request.get("questions")
    if not isinstance(questions, list) or not questions:
        return None
    call_id = ""
    calls = approval_request.get("tool_calls")
    if isinstance(calls, list) and calls and isinstance(calls[0], dict):
        call_id = str(calls[0].get("call_id") or "")
    return call_id, questions


def _latest_message_id(cur: Any, identity: ChatIdentity, role: str) -> str | None:
    cur.execute(
        """
        SELECT id FROM messages
        WHERE topic_id = %s AND user_id = %s AND role = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (identity.topic_id, identity.user_id, role),
    )
    row = cur.fetchone()
    if not row:
        return None
    return str(row[0])


def _upsert_message(
    cur: Any,
    *,
    message_id: str,
    role: str,
    content: str,
    identity: ChatIdentity,
    parent_id: str | None,
    metadata: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO messages (
            id, role, content, model, provider, user_id, topic_id, agent_id,
            parent_id, client_id, metadata, created_at, updated_at, accessed_at
        ) VALUES (
            %s, %s, %s, 'solo', 'openai', %s, %s, %s,
            %s, %s, %s::jsonb, now(), now(), now()
        )
        ON CONFLICT (id) DO UPDATE SET
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            updated_at = now(),
            accessed_at = now()
        """,
        (
            message_id,
            role,
            content,
            identity.user_id,
            identity.topic_id,
            identity.agent_id,
            parent_id,
            message_id,
            json.dumps(metadata),
        ),
    )


def write_final_reply(cur: Any, identity: ChatIdentity, content: str) -> str | None:
    """Upsert the terminal assistant row. Empty content leaves the table alone."""
    text = content.strip()
    if not text:
        return None
    resolved = resolve_identity(cur, identity)
    if resolved is None:
        return None
    message_id = final_message_id(resolved.run_id)
    cur.execute(
        """
        SELECT id, content FROM messages
        WHERE topic_id = %s AND user_id = %s AND role = 'assistant' AND id <> %s
          AND created_at > now() - interval '3 minutes'
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (resolved.topic_id, resolved.user_id, message_id),
    )
    recent = cur.fetchall()
    for row in recent:
        if str(row[1] or "").strip() == text:
            return str(row[0])
    if recent:
        newest_id, newest_content = str(recent[0][0]), str(recent[0][1] or "").strip()
        if newest_content in {"", "...", "LOADING_FLAT"}:
            cur.execute(
                """
                UPDATE messages
                SET content = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                """,
                (text, newest_id, resolved.user_id),
            )
            return newest_id
    parent_id = _latest_message_id(cur, resolved, "user")
    _upsert_message(
        cur,
        message_id=message_id,
        role="assistant",
        content=text,
        identity=resolved,
        parent_id=parent_id,
        metadata={"lca": {"run_id": identity.run_id, "kind": "final"}},
    )
    return message_id


def write_pending_question(
    cur: Any,
    identity: ChatIdentity,
    *,
    tool_call_id: str,
    questions: list[Any],
) -> str:
    """Stamp the ask card onto the tool row the UI already rendered.

    The live client inserts its own tool message. A second row with the
    same ``tool_call_id`` never becomes the card. Update that row. Insert
    ``lca-ask-<run>`` only when the client row is not there yet.
    """
    resolved = resolve_identity(cur, identity)
    if resolved is None:
        raise ValueError("topic has no user or agent to attach the ask card")
    arguments = json.dumps(
        {"lca_run_id": identity.run_id, "questions": questions},
        ensure_ascii=False,
    )
    state = json.dumps({"lca": {"run_id": identity.run_id, "status": "waiting_input"}})
    intervention = json.dumps({"status": "pending"})
    if tool_call_id:
        cur.execute(
            """
            SELECT id FROM message_plugins
            WHERE tool_call_id = %s AND user_id = %s
            ORDER BY id
            LIMIT 1
            """,
            (tool_call_id, resolved.user_id),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE message_plugins
                SET arguments = %s,
                    state = %s::jsonb,
                    intervention = %s::jsonb,
                    api_name = %s,
                    identifier = %s
                WHERE tool_call_id = %s AND user_id = %s
                """,
                (
                    arguments,
                    state,
                    intervention,
                    _ASK_API,
                    _ASK_IDENTIFIER,
                    tool_call_id,
                    resolved.user_id,
                ),
            )
            return str(existing[0])
    message_id = ask_message_id(resolved.run_id)
    parent_id = _latest_message_id(cur, resolved, "assistant") or _latest_message_id(
        cur, resolved, "user"
    )
    _upsert_message(
        cur,
        message_id=message_id,
        role="tool",
        content="",
        identity=resolved,
        parent_id=parent_id,
        metadata={"lca": {"run_id": identity.run_id, "kind": "ask"}},
    )
    cur.execute(
        """
        INSERT INTO message_plugins (
            id, tool_call_id, type, api_name, arguments, identifier,
            state, intervention, user_id
        ) VALUES (
            %s, %s, 'default', %s, %s, %s, %s::jsonb, %s::jsonb, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            tool_call_id = EXCLUDED.tool_call_id,
            arguments = EXCLUDED.arguments,
            state = EXCLUDED.state,
            intervention = EXCLUDED.intervention
        """,
        (
            message_id,
            tool_call_id or message_id,
            _ASK_API,
            arguments,
            _ASK_IDENTIFIER,
            state,
            intervention,
            resolved.user_id,
        ),
    )
    return message_id


def clear_pending_question(cur: Any, identity: ChatIdentity, *, approved: bool) -> None:
    """A finished run must not leave the ask card blocking the composer."""
    resolved = resolve_identity(cur, identity)
    if resolved is None:
        return
    status = "approved" if approved else "rejected"
    payload = json.dumps({"status": status})
    cur.execute(
        """
        UPDATE message_plugins
        SET intervention = %s::jsonb
        WHERE user_id = %s
          AND api_name = %s
          AND (
            id = %s
            OR state->'lca'->>'run_id' = %s
          )
        """,
        (
            payload,
            resolved.user_id,
            _ASK_API,
            ask_message_id(resolved.run_id),
            resolved.run_id,
        ),
    )


def lobehub_database_url() -> str | None:
    """The database that owns ``messages``.

    The kernel process does not inherit the LobeHub dev server's env.
    ``DATABASE_URL`` wins. The dev checkout's ``lobehub-ui/.env`` is the
    fallback, because that file is what the UI uses to read the same table.
    """
    from lca.infrastructure.persistence.postgres import database_url_from_env

    configured = database_url_from_env()
    if configured:
        return configured
    env_file = Path(__file__).resolve().parents[3] / "lobehub-ui" / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("DATABASE_URL="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value.startswith("postgres"):
                return value
    return None


def _connect(url: str) -> Any:
    """The kernel image has psycopg2. Newer images have psycopg."""
    try:
        import psycopg
    except ImportError:
        import psycopg2 as psycopg
    return psycopg.connect(url)


def _with_connection(fn: Any) -> None:
    url = lobehub_database_url()
    if not url:
        _log.warning("chat_projection_no_database")
        return
    conn = _connect(url)
    try:
        with conn.cursor() as cur:
            fn(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def persist_waiting_projection(session: Any) -> None:
    """Write the ask card before the run is marked paused."""
    identity = identity_from_session(session)
    pending = pending_question(getattr(session, "approval_request", None))
    if identity is None or pending is None:
        return
    tool_call_id, questions = pending

    def _write(cur: Any) -> None:
        write_pending_question(
            cur,
            identity,
            tool_call_id=tool_call_id,
            questions=questions,
        )

    try:
        await asyncio.to_thread(_with_connection, _write)
    except Exception:
        _log.warning("chat_projection_wait_failed", run_id=identity.run_id, exc_info=True)


def terminal_reply_text(session: Any) -> str:
    """Prefer ``session.output``. The respond text often lives only in the journal."""
    direct = str(getattr(session, "output", "") or "").strip()
    if direct:
        return direct
    spine = getattr(session, "spine_path", None)
    if spine is None:
        return ""
    journal = Path(spine).parent / "journal.json"
    if not journal.is_file():
        return ""
    try:
        document = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    for step in reversed(document.get("steps") or []):
        thinking = step.get("thinking") if isinstance(step, dict) else None
        if not isinstance(thinking, dict) or thinking.get("decision") != "respond":
            continue
        text = thinking.get("raw_response_preview")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


async def persist_terminal_projection(session: Any, *, success: bool) -> None:
    """Write the final reply and close the ask card. Safe to call twice."""
    identity = identity_from_session(session)
    if identity is None:
        return
    content = terminal_reply_text(session)

    def _write(cur: Any) -> None:
        if success:
            write_final_reply(cur, identity, content)
        clear_pending_question(cur, identity, approved=success)

    try:
        await asyncio.to_thread(_with_connection, _write)
    except Exception:
        _log.warning("chat_projection_terminal_failed", run_id=identity.run_id, exc_info=True)
