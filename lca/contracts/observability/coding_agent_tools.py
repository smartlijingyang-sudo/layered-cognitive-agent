"""Coding Agent Tools 契约 —— ADR-0065 §六 / PR-8。

7 个只读工具供 Coding Agent 调试使用,**read-only,无 journal.write 旁路**。
每个工具签名明确不接收 StampedEvent / JournalRecord writer;``check_no_journal_write_in_coding_agent``
AST 扫描兜底。

工具列表:
1. ``TraceInspectorTool`` — inspect_trace(focus/depth)
2. ``FailureExplainerTool`` — explain_failure(depth)
3. ``OptimizationFinderTool`` — find_optimization_candidates(limit)
4. ``PluginGraphRendererTool`` — render() → Mermaid
5. ``MinimalReproductionTool`` — export() → 因果链 + evidence refs
6. ``DiffContextTool`` — diff(run_id, step)
7. ``RunDiffTool`` — diff(run_id_a, run_id_b, step)

实现位置:``lca/layer0_infra/observability/coding_agent_tools/``(7 个 .py)。
Bundle:``lca/plugins/bundles/coding_agent_tools.py`` + ``bundles/coding-agent-tools.yaml``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class MinimalReproductionPackage:
    """失败因果链 + 必要 evidence refs;供离线复现。"""

    failure_seq: int = 0
    failure_event_type: str = ""
    causal_chain: tuple[int, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextDiff:
    """同 run 不同 step 的上下文差异。"""

    run_id: str = ""
    step_a: int = 0
    step_b: int = 0
    items_added: tuple[str, ...] = ()
    items_removed: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunDiff:
    """两次 run 同 step 的差异。"""

    run_id_a: str = ""
    run_id_b: str = ""
    step: int = 0
    prompt_hash_a: str = ""
    prompt_hash_b: str = ""
    delta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TraceInspectorTool(Protocol):
    """inspect_trace — 通用轨迹查看。"""

    def inspect_trace(
        self,
        *,
        run_id: str,
        focus: str = "all",
        depth: int = 24,
    ) -> dict[str, Any]:
        """返回 TraceReport 序列化(TraceInspector 现有 API)。"""


@runtime_checkable
class FailureExplainerTool(Protocol):
    """explain_failure — 失败路径投影。"""

    def explain_failure(self, *, run_id: str, depth: int = 24) -> dict[str, Any]: ...


@runtime_checkable
class OptimizationFinderTool(Protocol):
    """find_optimization_candidates — 按延迟/token/重试排序。"""

    def find_optimization_candidates(
        self, *, run_id: str, limit: int = 5
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class PluginGraphRendererTool(Protocol):
    """render — Mermaid 插件交互图。"""

    def render(self, *, run_id: str) -> str: ...


@runtime_checkable
class MinimalReproductionTool(Protocol):
    """export — 失败因果链 + evidence refs。"""

    def export(self, *, run_id: str) -> MinimalReproductionPackage: ...


@runtime_checkable
class DiffContextTool(Protocol):
    """diff — 同 run 不同 step 的 context 差异。"""

    def diff(self, *, run_id: str, step: int = 0) -> ContextDiff: ...


@runtime_checkable
class RunDiffTool(Protocol):
    """diff — 两次 run 同 step 差异。"""

    def diff(self, *, run_id_a: str, run_id_b: str, step: int = 0) -> RunDiff: ...


__all__ = [
    "ContextDiff",
    "FailureExplainerTool",
    "MinimalReproductionPackage",
    "MinimalReproductionTool",
    "OptimizationFinderTool",
    "PluginGraphRendererTool",
    "RunDiff",
    "RunDiffTool",
    "TraceInspectorTool",
]
