"""Process-local index for legacy gateway run sessions.

The index deliberately owns only ephemeral lookup concerns: session identity,
in-flight de-duplication, retention, and live-tail totals. Durable path
resolution and process-journal ownership live in separate collaborators so the
``RunRegistry`` facade no longer conflates three lifecycles.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from lca.contracts.models.core.plane import PlaneBindings

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession


DEFAULT_MAX_TERMINAL = 128
DEFAULT_TERMINAL_TTL_S = 3600.0
_TERMINAL_STATUS_VALUES = frozenset({"completed", "failed", "canceled"})


def run_dedup_key(
    *,
    user_text: str,
    mode: str,
    attachment_ids: Sequence[str] = (),
    agent_id: str = "",
) -> str:
    """Fingerprint concurrent duplicate carrier requests for one principal."""

    normalized = " ".join(user_text.strip().split())
    attachments = ",".join(
        sorted(str(item).strip() for item in attachment_ids if str(item).strip())
    )
    principal = agent_id.strip() or "solo"
    payload = f"{mode}\0{principal}\0{normalized}\0{attachments}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


class RunSessionIndex:
    """Own the process-local run cache and its in-flight lifecycle rules."""

    def __init__(
        self,
        *,
        max_terminal: int = DEFAULT_MAX_TERMINAL,
        terminal_ttl_s: float = DEFAULT_TERMINAL_TTL_S,
    ) -> None:
        self._sessions: dict[str, RunSession] = {}
        self._inflight_by_key: dict[str, str] = {}
        self._max_terminal = max_terminal
        self._terminal_ttl_s = terminal_ttl_s

    def put(self, session: RunSession) -> None:
        """Index one newly created session and mark its request as in flight."""

        self._sessions[session.run_id] = session
        self._inflight_by_key[_session_dedup_key(session)] = session.run_id

    def get(self, run_id: str) -> RunSession | None:
        """Return the local live session, if it has not been evicted."""

        return self._sessions.get(run_id)

    def sessions(self) -> tuple[RunSession, ...]:
        """Return a stable snapshot of locally retained sessions."""

        return tuple(self._sessions.values())

    def find_inflight_run(
        self,
        *,
        user_text: str,
        mode: str,
        attachment_ids: Sequence[str] = (),
        agent_id: str = "",
    ) -> RunSession | None:
        """Return an active duplicate request, clearing stale index entries."""

        key = run_dedup_key(
            user_text=user_text,
            mode=mode,
            attachment_ids=attachment_ids,
            agent_id=agent_id,
        )
        run_id = self._inflight_by_key.get(key)
        if run_id is None:
            return None
        session = self.get(run_id)
        if session is None or session.status.value not in {"pending", "running"}:
            self._inflight_by_key.pop(key, None)
            return None
        return session

    def clear_inflight(self, session_or_id: RunSession | str) -> None:
        """Release the duplicate-request lease for a terminal or paused run."""

        session = self.get(session_or_id) if isinstance(session_or_id, str) else session_or_id
        if session is None:
            return
        key = _session_dedup_key(session)
        if self._inflight_by_key.get(key) == session.run_id:
            self._inflight_by_key.pop(key, None)

    def mark_paused(self, session: RunSession) -> None:
        """Paused runs are resumable but no longer coalesce new requests."""

        self.clear_inflight(session)

    def prune(self, now: float | None = None) -> int:
        """Evict terminal runs by retention time and then by bounded capacity."""

        clock = time.time() if now is None else now
        terminal = [
            session
            for session in self._sessions.values()
            if session.status.value in _TERMINAL_STATUS_VALUES
        ]
        drop = [
            session.run_id
            for session in terminal
            if clock - (session.closed_at if session.closed_at is not None else clock)
            >= self._terminal_ttl_s
        ]
        kept = [session for session in terminal if session.run_id not in drop]
        kept.sort(key=lambda session: session.closed_at if session.closed_at is not None else 0.0)
        overflow = len(kept) - self._max_terminal
        if overflow > 0:
            drop.extend(session.run_id for session in kept[:overflow])
        for run_id in drop:
            session = self._sessions.pop(run_id, None)
            if session is not None:
                self.clear_inflight(session)
        return len(drop)

    def latest_bindings(self) -> PlaneBindings | None:
        """Return the most recent plane bindings from the local live cache."""

        for session in reversed(tuple(self._sessions.values())):
            if session.bindings is not None:
                return session.bindings
        return None

    def status_counts(self) -> dict[str, int]:
        """Count non-terminal sessions for carrier health projections."""

        counts = {"pending": 0, "running": 0, "waiting_input": 0}
        for session in self._sessions.values():
            if session.status.value in counts:
                counts[session.status.value] += 1
        return counts

    def live_tail_totals(self) -> dict[str, int]:
        """Aggregate per-run tail metrics without observing process projections."""

        subscribers = 0
        evicted = 0
        for session in self._sessions.values():
            subscribers += session.tail.subscriber_count
            evicted += session.tail.evicted
        return {"total_subscribers": subscribers, "total_evicted": evicted}


def _session_dedup_key(session: RunSession) -> str:
    """Build the single deduplication key from a session's immutable request data."""

    return run_dedup_key(
        user_text=session.user_text,
        mode=session.mode,
        attachment_ids=session.attachment_ids,
        agent_id=session.agent.agent_id,
    )


__all__ = [
    "DEFAULT_MAX_TERMINAL",
    "DEFAULT_TERMINAL_TTL_S",
    "RunSessionIndex",
    "run_dedup_key",
]
