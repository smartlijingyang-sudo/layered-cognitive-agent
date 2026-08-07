"""Gateway HTTP 契约 —— UI catalog 生成器的只读数据源。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateRunRequest:
    question: str
    mode: str = "board"
    track: str | None = None


@dataclass(frozen=True)
class CreateRunResponse:
    run_id: str
    trace_id: str
