"""默认 LoopProjectionDefinition 列表(ADR-0170 D5) + 出口实现(ADR-0172 D1/D5)。

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

ADR-0172 D1/D2/D5 增列(Exporter,默认不挂):
    - metrics        MetricsProjection
    - otel           OtelProjection
    - langfuse       LangfuseProjection

web-standard 默认不含 Exporter(ADR-0172 P3);oii-debug / genai-traced /
coding-agent / langfuse-eval 等 profile 按需 ``register_default_exporters(host)``。

新增 deriver / exporter 零改 ``loop_cursor.py``(I-PROJ-5)。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import LoopProjectionDefinition
from lca.infrastructure.observability.spine.event_record import EventRecord

if TYPE_CHECKING:
    from lca.infrastructure.observability.loop_cursor.projection_host import (
        ProjectionToken,
        StdProjectionHost,
    )


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
    last_endpoint: str | None = None  # reducer purity per ADR-0170 D1


class _GraphProjection:
    """Edges-tuple reducer for the phase graph.

    ADR-0170 D1 reducer purity: ``apply`` returns a new ``_GraphState``
    and never mutates ``self``. The previous edge's terminal endpoint
    lives in the state itself (``last_endpoint``) so two consecutive
    calls with the same input produce identical output, satisfying
    the close-set / reducer-purity invariant.
    """

    key = "graph"
    version = 1

    def init(self) -> _GraphState:
        return _GraphState(last_endpoint=None)

    def apply(
        self,
        state: _GraphState,
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> _GraphState:
        prev = state.last_endpoint
        edges = list(state.edges)
        if prev is not None:
            edges.append((prev, record.execution_point))
        return _GraphState(
            edges=edges,
            last_endpoint=record.execution_point,
        )

    def view(self, state: _GraphState) -> dict[str, Any]:
        return {"key": self.key, "version": self.version, "edges": list(state.edges)}

    def restore(self, state: _GraphState) -> _GraphState:
        return _GraphState(last_endpoint=None)


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


# ── ADR-0172 · Exporter 默认 key 表(D2/P3) ───────────────────────────
# 钉死 Exporter 默认注册 key;web-standard 默认不含(P3 — 避免无凭证 SDK 报错);
# oii-debug / genai-traced / coding-agent / langfuse-eval 等 profile 按需加载。
DEFAULT_EXPORTER_KEYS: tuple[str, ...] = ("metrics", "otel", "langfuse")


def default_exporter_definitions() -> list[LoopProjectionDefinition]:
    """ADR-0172 D1 默认 Exporter 注册清单。

    仅构造,不在 web-standard 中自动注册;由 profile YAML 触发
    ``register_default_exporters(host)`` 调用。
    """
    # 局部 import 避免循环 + 与 metrics_projection / otel_projection
    # / langfuse_projection 模块加载顺序解耦(它们仅在 register 时需要)。
    from lca.infrastructure.observability.loop_cursor.projections.langfuse_projection import (
        LangfuseProjection,
    )
    from lca.infrastructure.observability.loop_cursor.projections.metrics_projection import (
        MetricsProjection,
    )
    from lca.infrastructure.observability.loop_cursor.projections.otel_projection import (
        OtelProjection,
    )

    return [
        MetricsProjection(),
        OtelProjection(),
        LangfuseProjection(),
    ]


def default_exporter_keys() -> Iterable[str]:
    """Exporter 默认 key 列表(测试 seam)。"""
    return DEFAULT_EXPORTER_KEYS


def register_default_exporters(
    host: StdProjectionHost,
) -> list[ProjectionToken]:
    """注册 ADR-0172 D1 默认 Exporter 清单到 host;返回 disposer tokens。

    Profile YAML `projection_host.initial` 段加载时调用;
    web-standard 不调,保持默认不含 Exporter(ADR-0172 P3)。
    """
    tokens: list[ProjectionToken] = []
    for definition in default_exporter_definitions():
        tokens.append(host.register(definition))
    return tokens


__all__ = [
    "DEFAULT_EXPORTER_KEYS",
    "default_exporter_definitions",
    "default_exporter_keys",
    "default_projection_definitions",
    "default_projection_keys",
    "register_default_exporters",
]
