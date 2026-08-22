"""Run session aggregate + the one process-wide run index."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from gateway.runs.identity import AgentRef, default_agent_ref
from gateway.runs.live import LiveTail
from lca.contracts.models.core.conversation import ConversationTurn
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.observability.run_locator import RunLocator
from lca.layer0_infra.observability import BoundObservability

_RUNS_ROOT = Path("traces")  # ADR-0065 §七:locator root,runs/ 是其子目录
_DEFAULT_MAX_TERMINAL = 128
_DEFAULT_TERMINAL_TTL_S = 3600.0


def run_dedup_key(
    *,
    user_text: str,
    mode: str,
    attachment_ids: Sequence[str] = (),
    agent_id: str = "",
) -> str:
    """Fingerprint for coalescing concurrent duplicate LobeHub requests.

    ``agent_id`` is part of the key: two principals never share an inflight Run.
    """
    normalized = " ".join(user_text.strip().split())
    attachments = ",".join(sorted(str(i).strip() for i in attachment_ids if str(i).strip()))
    principal = agent_id.strip() or "solo"
    payload = f"{mode}\0{principal}\0{normalized}\0{attachments}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    def to_lobehub_session_status(self) -> str:
        return _LOBEHUB_STATUS_MAP[self]


_TERMINAL = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED})

_LOBEHUB_STATUS_MAP: dict[RunStatus, str] = {
    RunStatus.PENDING: "running",
    RunStatus.RUNNING: "running",
    RunStatus.WAITING_INPUT: "waiting_input",
    RunStatus.COMPLETED: "completed",
    RunStatus.FAILED: "error",
    RunStatus.CANCELED: "interrupted",
}


@dataclass
class RunSession:
    """One Run: hub, tail, status, and the task that drives them."""

    run_id: str
    trace_id: str
    jsonl_path: Path
    tail: LiveTail
    question: str
    user_text: str
    mode: str
    hub: BoundObservability | None = None
    prior_turns: tuple[ConversationTurn, ...] = field(default_factory=tuple)
    attachment_ids: tuple[str, ...] = field(default_factory=tuple)
    agent: AgentRef = field(default_factory=default_agent_ref)
    status: RunStatus = RunStatus.PENDING
    error: str = ""
    task: asyncio.Task[Any] | None = None
    cancel_requested: bool = False
    declarative_checkpoint: Any = None
    runnable: Any = None
    approval_request: dict[str, Any] | None = None
    closed_at: float | None = None
    bindings: PlaneBindings | None = None
    device_id: str = ""
    plane: str = ""
    extra_plane: str = ""
    execution_target: str = ""
    started_at: float = 0.0
    locator: RunLocator | None = None  # ADR-0065 PR-11:run 级 locator 引用


class RunRegistry:
    """The only Run index. No parallel module-level session tables.

    ADR-0065 PR-11: ``RunLocator`` 是 run_id → 物理路径的唯一契约;Registry
    持有 locator 实例,所有路径解析(jsonl / manifest / evidence /
    materialization)都走它。默认 locator 是 ``FilesystemRunLocator(root=traces)``;
    测试隔离可通过 ``locator=`` 注入临时 root。
    """

    def __init__(
        self,
        *,
        locator: RunLocator | None = None,
        max_terminal: int = _DEFAULT_MAX_TERMINAL,
        terminal_ttl_s: float = _DEFAULT_TERMINAL_TTL_S,
    ) -> None:
        self._runs: dict[str, RunSession] = {}
        self._inflight_by_key: dict[str, str] = {}
        if locator is None:
            from lca.layer0_infra.observability.run_locator_fs import FilesystemRunLocator

            locator = FilesystemRunLocator(root=_RUNS_ROOT)
        self._locator: RunLocator = locator
        # ensure runs/ exists under locator root
        self._locator.storage_root.mkdir(parents=True, exist_ok=True)
        (self._locator.storage_root / "runs").mkdir(parents=True, exist_ok=True)
        self._max_terminal = max_terminal
        self._terminal_ttl_s = terminal_ttl_s
        # ADR-0065 PR-5: ProcessJournal 实例化走 _journal_factory。
        from gateway.runs._journal_factory import get_or_create_process_journal

        self.journal = get_or_create_process_journal(registry_journal=None)

    def latest_bindings(self) -> PlaneBindings | None:
        for session in reversed(list(self._runs.values())):
            if session.bindings is not None:
                return session.bindings
        return None

    def prune(self, now: float | None = None) -> int:
        """Drop terminal sessions past TTL or over the cap. Running/HIL stay."""
        clock = time.time() if now is None else now
        terminal = [session for session in self._runs.values() if session.status in _TERMINAL]
        drop: list[str] = []
        for session in terminal:
            closed = session.closed_at if session.closed_at is not None else clock
            if clock - closed >= self._terminal_ttl_s:
                drop.append(session.run_id)
        kept = [session for session in terminal if session.run_id not in drop]
        kept.sort(key=lambda session: session.closed_at if session.closed_at is not None else 0.0)
        overflow = len(kept) - self._max_terminal
        if overflow > 0:
            drop.extend(session.run_id for session in kept[:overflow])
        for run_id in drop:
            doomed = self._runs.get(run_id)
            if doomed is None:
                continue
            del self._runs[run_id]
            self.clear_inflight(doomed)
        return len(drop)

    def put(self, session: RunSession) -> None:
        self._runs[session.run_id] = session
        key = run_dedup_key(
            user_text=session.user_text,
            mode=session.mode,
            attachment_ids=session.attachment_ids,
            agent_id=session.agent.agent_id,
        )
        self._inflight_by_key[key] = session.run_id

    def find_inflight_run(
        self,
        *,
        user_text: str,
        mode: str,
        attachment_ids: Sequence[str] = (),
        agent_id: str = "",
    ) -> RunSession | None:
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
        if session is None or session.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            self._inflight_by_key.pop(key, None)
            return None
        return session

    def clear_inflight(self, session_or_id: RunSession | str) -> None:
        if isinstance(session_or_id, str):
            session = self._runs.get(session_or_id)
            if session is None:
                return
        else:
            session = session_or_id
        key = run_dedup_key(
            user_text=session.user_text,
            mode=session.mode,
            attachment_ids=session.attachment_ids,
            agent_id=session.agent.agent_id,
        )
        if self._inflight_by_key.get(key) == session.run_id:
            self._inflight_by_key.pop(key, None)

    def mark_paused(self, session: RunSession) -> None:
        self.clear_inflight(session)

    def get(self, run_id: str) -> RunSession | None:
        return self._runs.get(run_id)

    def sessions(self) -> tuple[RunSession, ...]:
        return tuple(self._runs.values())

    def locator(self) -> RunLocator:
        return self._locator

    def jsonl_path_for(self, run_id: str) -> Path:
        return self._locator.journal_path(run_id)

    def manifest_path_for(self, run_id: str) -> Path:
        return self._locator.manifest_path(run_id)

    def evidence_dir_for(self, run_id: str) -> Path:
        return self._locator.evidence_dir(run_id)

    def materialization_dir_for(
        self, run_id: str, *, generator_id: str, generator_version: str
    ) -> Path:
        return self._locator.materialization_dir(
            run_id, generator_id=generator_id, generator_version=generator_version
        )

    def update_latest_pointer(self, run_id: str) -> None:
        self._locator.update_latest_pointer(run_id)

    def summary(self, run_id: str) -> dict[str, Any] | None:
        session = self.get(run_id)
        if session is None:
            return None
        payload: dict[str, Any] = {
            "run_id": session.run_id,
            "trace_id": session.trace_id,
            "status": session.status.value,
            "session_status": session.status.to_lobehub_session_status(),
            "mode": session.mode,
            "agent": {"id": session.agent.agent_id, "name": session.agent.name},
            "question": session.question,
            "error": session.error,
        }
        if session.approval_request is not None:
            payload["approval_request"] = session.approval_request
        return payload

    def status_counts(self) -> dict[str, int]:
        counts = {"pending": 0, "running": 0, "waiting_input": 0}
        for session in self._runs.values():
            if session.status.value in counts:
                counts[session.status.value] += 1
        return counts

    def live_totals(self) -> dict[str, int]:
        subscribers = 0
        evicted = 0
        for session in self._runs.values():
            subscribers += session.tail.subscriber_count
            evicted += session.tail.evicted
        return {
            "total_subscribers": subscribers,
            "total_evicted": evicted,
            "journal_subscribers": self.journal.tail.subscriber_count,
        }
