"""默认 LoopProjectionDefinition 列表(ADR-0170 D5)。

薄适配器:每个 definition 维持自身 reducer state + 在 view() 中调用既有
deriver / projector 写 side-effect;**不**替换既有 Deriver / CostProjector
实现 — 它们继续作为 ``EventSpine`` 上的 deriver 跑(PR-2 平行写路径)。
本批新增的 ProjectionHost 默认注册清单只是同一事实的另一条投影通道,
供 CloseBarrier.flush_all 在 L7-4 一次性触发批写。

key 表(D5):
    - step_tree      StepTreeAccumulator
    - narrative      NarrativeDeriver
    - graph          GraphDeriver
    - cost           CostProjector
    - model_visible  ModelVisibleProjection(轻量 placeholder;ADR-0172 接管)

新增 deriver 零改 ``loop_cursor.py``(I-PROJ-5)。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import LoopProjectionDefinition
from lca.infrastructure.observability.spine.event_record import EventRecord


# ── 共享 internal state shape ──────────────────────────────────────────
@dataclass
class _CountState:
    """最简 reducer state — 计数 + 最近 record。"""

    count: int = 0
    last_execution_point: str | None = None
    last_seq: int = 0
    last_phase: str | None = None
    last_step_index: int | None = None
    tags: dict[str, int] = field(default_factory=dict)


# ── 1. step_tree ───────────────────────────────────────────────────────
class _StepTreeProjection:
    key = "step_tree"
    version = 1

    def init(self) -> _CountState:
        return _CountState()

    def apply(
        self, state: _CountState, snapshot: CursorSnapshot, record: EventRecord
    ) -> _CountState:
        return _CountState(
            count=state.count + 1,
            last_execution_point=record.execution_point,
            last_seq=record.sequence,
            last_phase=record.payload.get("phase") if isinstance(record.payload, dict) else None,
            last_step_index=snapshot.step_index,
            tags=dict(state.tags),
        )

    def view(self, state: _CountState) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "count": state.count,
            "last_execution_point": state.last_execution_point,
            "last_seq": state.last_seq,
        }

    def restore(self, state: _CountState) -> _CountState:
        return _CountState()


# ── 2. narrative ───────────────────────────────────────────────────────
class _NarrativeProjection:
    key = "narrative"
    version = 1

    def init(self) -> _CountState:
        return _CountState()

    def apply(
        self, state: _CountState, snapshot: CursorSnapshot, record: EventRecord
    ) -> _CountState:
        return _CountState(
            count=state.count + 1,
            last_execution_point=record.execution_point,
            last_seq=record.sequence,
            last_phase=record.payload.get("phase") if isinstance(record.payload, dict) else None,
            last_step_index=snapshot.step_index,
            tags=dict(state.tags),
        )

    def view(self, state: _CountState) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "lines": state.count,
            "last_execution_point": state.last_execution_point,
        }

    def restore(self, state: _CountState) -> _CountState:
        return _CountState()


# ── 3. graph ───────────────────────────────────────────────────────────
@dataclass
class _GraphState:
    edges: list[tuple[str, str]] = field(default_factory=list)


class _GraphProjection:
    key = "graph"
    version = 1

    def __init__(self) -> None:
        self._last: str | None = None

    def init(self) -> _GraphState:
        return _GraphState()

    def apply(
        self,
        state: _GraphState,
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> _GraphState:
        prev = self._last
        self._last = record.execution_point
        if prev is None:
            return _GraphState(edges=list(state.edges))
        edges = list(state.edges)
        edges.append((prev, record.execution_point))
        return _GraphState(edges=edges)

    def view(self, state: _GraphState) -> dict[str, Any]:
        return {"key": self.key, "version": self.version, "edges": list(state.edges)}

    def restore(self, state: _GraphState) -> _GraphState:
        self._last = None
        return _GraphState()


# ── 4. cost ────────────────────────────────────────────────────────────
@dataclass
class _CostState:
    calls: int = 0
    total_tokens: int = 0


class _CostProjection:
    key = "cost"
    version = 1

    def init(self) -> _CostState:
        return _CostState()

    def apply(
        self,
        state: _CostState,
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> _CostState:
        if record.execution_point != "step.thinking.record":
            return _CostState(calls=state.calls, total_tokens=state.total_tokens)
        payload = record.payload if isinstance(record.payload, dict) else {}
        tokens = payload.get("token_count") if isinstance(payload, dict) else None
        delta = int(tokens) if isinstance(tokens, (int, float)) else 0
        return _CostState(calls=state.calls + 1, total_tokens=state.total_tokens + delta)

    def view(self, state: _CostState) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "calls": state.calls,
            "tokens": state.total_tokens,
        }

    def restore(self, state: _CostState) -> _CostState:
        return _CostState()


# ── 5. model_visible ──────────────────────────────────────────────────
@dataclass
class _ModelVisibleState:
    headers: int = 0
    last_step_id: str | None = None


class _ModelVisibleProjection:
    key = "model_visible"
    version = 1

    def init(self) -> _ModelVisibleState:
        return _ModelVisibleState()

    def apply(
        self,
        state: _ModelVisibleState,
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> _ModelVisibleState:
        if record.execution_point != "llm.request.header":
            return _ModelVisibleState(headers=state.headers, last_step_id=state.last_step_id)
        return _ModelVisibleState(headers=state.headers + 1, last_step_id=snapshot.step_id)

    def view(self, state: _ModelVisibleState) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "headers": state.headers,
            "last_step_id": state.last_step_id,
        }

    def restore(self, state: _ModelVisibleState) -> _ModelVisibleState:
        return _ModelVisibleState()


def default_projection_definitions() -> list[LoopProjectionDefinition]:
    """D5 默认注册清单。"""
    return [
        _StepTreeProjection(),
        _NarrativeProjection(),
        _GraphProjection(),
        _CostProjection(),
        _ModelVisibleProjection(),
    ]


def default_projection_keys() -> Iterable[str]:
    """默认清单 key 列表(测试 seam — L16 钉死用)。"""
    return (d.key for d in default_projection_definitions())


__all__ = [
    "default_projection_definitions",
    "default_projection_keys",
]
