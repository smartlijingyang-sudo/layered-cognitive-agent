"""Run 会话注册表 —— 类型化 EventBus 广播 + jsonl 持久化（断线续传）。

Refactored: 从字符串帧（``frames: list[str]``）升级为类型化事件
（``EventBus``）。HTTP 层直接消费 ``StampedEvent``，不再需要
parse JSON → restore event 的反序列化步骤。
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from gateway.events import EventBus
from lca.contracts.models.core.conversation import ConversationTurn
from lca.layer0_infra.observability import ObservabilityHub

_RUNS_DIR = Path("traces/runs")


def run_dedup_key(
    *,
    user_text: str,
    mode: str,
    attachment_ids: Sequence[str] = (),
) -> str:
    """Stable fingerprint for coalescing **concurrent** duplicate LobeHub requests.

    Uses the last user turn only — not attachment prefixes or prior conversation.
    Only applies while a run is PENDING/RUNNING; sequential re-requests after
    completion are prevented by Mode A closed-loop (no client tool loop), not
    by this key.
    """
    normalized = " ".join(user_text.strip().split())
    attachments = ",".join(sorted(str(i).strip() for i in attachment_ids if str(i).strip()))
    payload = f"{mode}\0{normalized}\0{attachments}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    def to_lobehub_session_status(self) -> str:
        """映射到 LobeHub ``SessionStatus`` 词表（G2A 路径）。"""
        return _LOBEHUB_STATUS_MAP[self]


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
    """单次 run 的 EventBus 广播会话。"""

    run_id: str
    trace_id: str
    jsonl_path: Path
    hub: ObservabilityHub
    question: str
    user_text: str
    mode: str
    prior_turns: tuple[ConversationTurn, ...] = field(default_factory=tuple)
    attachment_ids: tuple[str, ...] = field(default_factory=tuple)
    status: RunStatus = RunStatus.PENDING
    error: str = ""
    task: asyncio.Task[Any] | None = None
    cancel_requested: bool = False
    bus: EventBus = field(default_factory=EventBus)
    # HIL pause/resume: populated when status == WAITING_INPUT.
    snapshot: Any = None
    runnable: Any = None
    approval_request: dict[str, Any] | None = None

    def close_bus(self) -> None:
        """Signal all subscribers that the run has ended."""
        self.bus.close()

    async def event_stream(self, last_event_id: int = 0) -> AsyncIterator[Any]:
        """Typed event stream — supports disconnect-replay via seq."""
        async for stamped in self.bus.subscribe(after_seq=last_event_id):
            yield stamped


class RunRegistry:
    """进程内 run 索引（MVP 单租户）。"""

    def __init__(self, runs_dir: Path | None = None) -> None:
        self._runs: dict[str, RunSession] = {}
        self._inflight_by_key: dict[str, str] = {}
        self._runs_dir = runs_dir if runs_dir is not None else _RUNS_DIR
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def put(self, session: RunSession) -> None:
        self._runs[session.run_id] = session
        key = run_dedup_key(
            user_text=session.user_text,
            mode=session.mode,
            attachment_ids=session.attachment_ids,
        )
        self._inflight_by_key[key] = session.run_id

    def find_inflight_run(
        self,
        *,
        user_text: str,
        mode: str,
        attachment_ids: Sequence[str] = (),
    ) -> RunSession | None:
        """Return an active run for the same user turn/mode, if LobeHub duplicated the request."""
        key = run_dedup_key(user_text=user_text, mode=mode, attachment_ids=attachment_ids)
        run_id = self._inflight_by_key.get(key)
        if run_id is None:
            return None
        session = self.get(run_id)
        if session is None or session.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            self._inflight_by_key.pop(key, None)
            return None
        return session

    def clear_inflight(self, session: RunSession) -> None:
        key = run_dedup_key(
            user_text=session.user_text,
            mode=session.mode,
            attachment_ids=session.attachment_ids,
        )
        if self._inflight_by_key.get(key) == session.run_id:
            self._inflight_by_key.pop(key, None)

    def mark_paused(self, session: RunSession) -> None:
        """Remove from inflight dedup but keep session alive for HIL resume."""
        self.clear_inflight(session)

    def get(self, run_id: str) -> RunSession | None:
        return self._runs.get(run_id)

    def runs_dir(self) -> Path:
        return self._runs_dir

    def jsonl_path_for(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.jsonl"

    def summary(self, run_id: str) -> dict[str, Any] | None:
        session = self.get(run_id)
        if session is None:
            return None
        return {
            "run_id": session.run_id,
            "trace_id": session.trace_id,
            "status": session.status.value,
            "session_status": session.status.to_lobehub_session_status(),
            "mode": session.mode,
            "question": session.question,
            "error": session.error,
        }

    async def event_stream(
        self,
        run_id: str,
        last_event_id_header: str | None,
    ) -> AsyncIterator[Any]:
        """Typed event stream for an HTTP client."""
        from lca.layer0_infra.observability.journal.sse_frames import parse_last_event_id

        session = self.get(run_id)
        if session is None:
            return
        after = parse_last_event_id(last_event_id_header)
        async for stamped in session.bus.subscribe(after_seq=after):
            yield stamped
