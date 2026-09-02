"""Legacy run-session aggregate and its compatibility registry facade.

``RunSession`` remains the carrier-facing aggregate for one live run.  The
registry intentionally delegates its three independent lifecycles: ephemeral
run lookup to ``RunSessionIndex``, durable paths to ``RunLocator``, and the
process-wide live journal to ``ProcessJournalBinding``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lca.contracts.models.core.conversation import ConversationTurn
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.observability.close_barrier import CloseReason
from lca.contracts.observability.run_journal import (
    LiveRunProjection,
    ProcessJournalProjection,
    RunJournalFactory,
)
from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability import BoundObservability
from lca.infrastructure.observability.loop_cursor import (
    reset_model_visible_capture,
    reset_run_cursor,
)
from lca.plugins.transport.webserver.handlers.runs.observability.identity import (
    AgentRef,
    default_agent_ref,
)
from lca.plugins.transport.webserver.handlers.runs.observability.journal_projection_binding import (
    ProcessJournalBinding,
)
from lca.plugins.transport.webserver.handlers.runs.session.health import RunHealthProjection
from lca.plugins.transport.webserver.handlers.runs.session.index import (
    DEFAULT_MAX_TERMINAL,
    DEFAULT_TERMINAL_TTL_S,
    RunSessionIndex,
    run_dedup_key,
)
from lca.plugins.transport.webserver.handlers.runs.session.projection import summary_for_session

_RUNS_ROOT = Path("traces")  # ADR-0065 §七: locator root, runs/ 是其子目录


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    def to_lobehub_session_status(self) -> str:
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
    """Carrier-facing mutable state for one legacy run."""

    run_id: str
    trace_id: str
    spine_path: Path
    tail: LiveRunProjection
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
    snapshot: Any = None
    runnable: Any = None
    approval_request: dict[str, Any] | None = None
    closed_at: float | None = None
    bindings: PlaneBindings | None = None
    device_id: str = ""
    plane: str = ""
    extra_plane: str = ""
    execution_target: str = ""
    started_at: float = 0.0
    locator: RunLocator | None = None  # ADR-0065 PR-11: run 级 locator 引用
    thread_tree_writer: object | None = None  # ADR-0167 D11: per-run StepTreeAccumulatorDeriver
    coordinator: object | None = None  # ADR-0167 D11: StepCoordinator (Agent 唯一写入口)
    loop_cursor: object | None = None  # ADR-0169 §D11 PR-1.5: LoopCursor(写入 cursor 的入口)
    loop_cursor_token: object | None = (
        None  # ADR-0169 §D11 PR-1.5: ContextVar reset token (close 时释放)
    )
    model_visible_capture: object | None = (
        None  # ADR-0169 PR-12.5: per-run ModelVisibleCapture 引用
    )
    model_visible_capture_token: object | None = (
        None  # ADR-0169 PR-12.7: ContextVar reset token (close 时释放)
    )

    _closed: bool = field(
        default=False,
        repr=False,
        init=False,
    )

    def close(self, reason: CloseReason) -> bool:
        """释放 run-local ContextVar token,run 终止时由 terminalizer 调一次。

        PR-1.5 / PR-12.5 builder 里 ``install_run_cursor`` 与
        ``install_model_visible_capture`` 配对操作。原本两者只 set token 不
        reset,在多 run 时 ContextVar 内部字典无限增长(单进程 leak)。
        是 PR-12.7 close hook 入口,被 :class:`RunTerminalizer.terminalize`
        在 finalize 后调一次。

        ADR-0169 D5/L10 + PR-12.7:reset 不可重复 — 调用后清字段,
        第二次调用返回 ``False`` 告知 terminalizer 「已 close」,防双 close 重入。

        Returns
        -------
        bool
            ``True``  首次 close,token 已释放;
            ``False`` 已 close 过,本调用幂等 no-op。
        """
        if self._closed:
            return False
        if self.loop_cursor_token is not None:
            with contextlib.suppress(Exception):
                reset_run_cursor(self.loop_cursor_token)
            self.loop_cursor_token = None
        if self.model_visible_capture_token is not None:
            with contextlib.suppress(Exception):
                reset_model_visible_capture(self.model_visible_capture_token)
            self.model_visible_capture_token = None
        self._closed = True
        return True

    step_tree_bundle: object | None = (
        None  # ADR-0164 Phase 6: step-tree write bundle (legacy, 兼容)
    )


class RunRegistry:
    """Compatibility facade over run index, durable locator, and process journal.

    The public API stays stable for the legacy gateway while each collaborator
    has a single lifecycle.  No parallel module-level session tables exist.
    """

    def __init__(
        self,
        *,
        locator: RunLocator | None = None,
        max_terminal: int = DEFAULT_MAX_TERMINAL,
        terminal_ttl_s: float = DEFAULT_TERMINAL_TTL_S,
    ) -> None:
        if locator is None:
            from lca.infrastructure.observability.backends.run_locator_fs import (
                FilesystemRunLocator,
            )

            locator = FilesystemRunLocator(root=_RUNS_ROOT)
        self._locator: RunLocator = locator
        self._locator.storage_root.mkdir(parents=True, exist_ok=True)
        (self._locator.storage_root / "runs").mkdir(parents=True, exist_ok=True)
        self._index = RunSessionIndex(
            max_terminal=max_terminal,
            terminal_ttl_s=terminal_ttl_s,
        )
        self._process_journal = ProcessJournalBinding()
        self._health = RunHealthProjection(
            index=self._index,
            process_journal=self._process_journal,
        )

    def latest_bindings(self) -> PlaneBindings | None:
        """Return the newest bound plane configuration from the local run cache."""

        return self._index.latest_bindings()

    def prune(self, now: float | None = None) -> int:
        """Evict retained terminal session handles using the index retention policy."""

        return self._index.prune(now=now)

    def put(self, session: RunSession) -> None:
        """Register a new session in the process-local index."""

        self._index.put(session)

    def find_inflight_run(
        self,
        *,
        user_text: str,
        mode: str,
        attachment_ids: Sequence[str] = (),
        agent_id: str = "",
    ) -> RunSession | None:
        """Return a coalescible in-flight session, if one exists."""

        return self._index.find_inflight_run(
            user_text=user_text,
            mode=mode,
            attachment_ids=attachment_ids,
            agent_id=agent_id,
        )

    def clear_inflight(self, session_or_id: RunSession | str) -> None:
        """Release a session's process-local deduplication lease."""

        self._index.clear_inflight(session_or_id)

    def mark_paused(self, session: RunSession) -> None:
        """Mark a session resumable without keeping its request coalesced."""

        self._index.mark_paused(session)

    def get(self, run_id: str) -> RunSession | None:
        """Return the in-process session handle, if retained."""

        return self._index.get(run_id)

    def sessions(self) -> tuple[RunSession, ...]:
        """Return a stable snapshot of retained session handles."""

        return self._index.sessions()

    def locator(self) -> RunLocator:
        """Return the sole run-id-to-durable-path resolver."""

        return self._locator

    @property
    def journal(self) -> ProcessJournalProjection:
        """Return the explicitly bound process-level real-time projection."""

        return self._process_journal.journal

    def bind_process_journal(self, factory: RunJournalFactory) -> JournalProjector:
        """Return one per-run binding into the shared process projection."""

        return self._process_journal.bind(factory)

    def spine_path_for(self, run_id: str) -> Path:
        """Resolve the run's spine SSOT path (events.jsonl) via the durable locator."""

        return self._locator.events_path(run_id)

    def manifest_path_for(self, run_id: str) -> Path:
        """Resolve a run manifest path through the durable locator."""

        return self._locator.manifest_path(run_id)

    def evidence_dir_for(self, run_id: str) -> Path:
        """Resolve a run evidence directory through the durable locator."""

        return self._locator.evidence_dir(run_id)

    def materialization_dir_for(
        self,
        run_id: str,
        *,
        generator_id: str,
        generator_version: str,
    ) -> Path:
        """Resolve the versioned output directory through the durable locator."""

        return self._locator.materialization_dir(
            run_id,
            generator_id=generator_id,
            generator_version=generator_version,
        )

    def update_latest_pointer(self, run_id: str) -> None:
        """Delegate latest-run materialization to the durable locator."""

        self._locator.update_latest_pointer(run_id)

    def summary(self, run_id: str) -> dict[str, Any] | None:
        """Return the carrier projection for one retained session."""

        session = self.get(run_id)
        return None if session is None else summary_for_session(session)

    def status_counts(self) -> dict[str, int]:
        """Return carrier health counts from the in-memory index."""

        return self._health.status_counts()

    def live_totals(self) -> dict[str, int]:
        """Return the carrier health projection from the dedicated owner."""

        return self._health.live_totals()


__all__ = ["RunRegistry", "RunSession", "RunStatus", "run_dedup_key"]
