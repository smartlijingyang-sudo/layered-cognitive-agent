"""Run 会话注册表 —— 多订阅者 SSE 广播 + jsonl 持久化（断线续传）。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.journal.sse_frames import (
    SSE_SENTINEL,
    frames_after_seq,
    parse_last_event_id,
)

_RUNS_DIR = Path("traces/runs")
_MAX_BUFFERED_FRAMES = 4096
_MAX_SUBSCRIBER_QUEUE = 256


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class RunSession:
    """单次 run 的 SSE 广播会话。"""

    run_id: str
    trace_id: str
    jsonl_path: Path
    hub: ObservabilityHub
    question: str
    mode: str
    # CreateRun 附件 id：execute 时 bind 进 run_attachment_scope，沙箱自动挂载。
    attachment_ids: tuple[str, ...] = field(default_factory=tuple)
    status: RunStatus = RunStatus.PENDING
    error: str = ""
    task: asyncio.Task[Any] | None = None
    cancel_requested: bool = False
    frames: list[str] = field(default_factory=list)
    _subscribers: list[asyncio.Queue[str | None]] = field(default_factory=list)
    _closed: bool = False

    def emit(self, frame: str | None) -> None:
        """SSEJournalProjector 回调：缓冲 + 广播。"""
        if frame is None:
            self._close_subscribers()
            return
        if len(self.frames) >= _MAX_BUFFERED_FRAMES:
            self.frames.pop(0)
        self.frames.append(frame)
        dead: list[asyncio.Queue[str | None]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self._subscribers.remove(queue)

    def _close_subscribers(self) -> None:
        if self._closed:
            return
        self._closed = True
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(SSE_SENTINEL)
        self._subscribers.clear()

    async def subscribe(self, last_event_id: int = 0) -> AsyncIterator[str]:
        """回放 seq > last_event_id 的帧，再挂接实时广播。"""
        for frame in frames_after_seq(self.frames, last_event_id):
            yield frame
        if self._closed:
            return
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=_MAX_SUBSCRIBER_QUEUE)
        self._subscribers.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


class RunRegistry:
    """进程内 run 索引（MVP 单租户）。"""

    def __init__(self, runs_dir: Path | None = None) -> None:
        self._runs: dict[str, RunSession] = {}
        self._runs_dir = runs_dir if runs_dir is not None else _RUNS_DIR
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def put(self, session: RunSession) -> None:
        self._runs[session.run_id] = session

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
            "mode": session.mode,
            "question": session.question,
            "error": session.error,
        }

    async def event_stream(
        self,
        run_id: str,
        last_event_id_header: str | None,
    ) -> AsyncIterator[str]:
        session = self.get(run_id)
        if session is None:
            yield 'event: error\ndata: {"message":"run not found"}\n\n'
            return
        after = parse_last_event_id(last_event_id_header)
        async for frame in session.subscribe(after):
            yield frame
