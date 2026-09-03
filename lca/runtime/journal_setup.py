"""Runtime factory: 构造一个已 ``bind_run`` 的 StepCoordinator (ADR-0167 D11)。

删除说明
--------
ADR-0167 D11 / PR-3 删除了 ``StepLifecycleStore`` 双写桥(原
``lca.runtime.step_lifecycle``); spine ``<run_id>.spine.jsonl`` 是 SSOT, 业务层
唯一入口是 :class:`StepCoordinator` (Protocol + registry 解引用)。
本模块负责在 run 创建期构造一个最小、最窄形态的 coordinator。

- ``build_step_coordinator`` —— 给定 WritableFaceRegistry + run_id +
  trace_id + metadata, 构造一个已 ``bind_run`` 的 StepCoordinator。
  不依赖 transport, 不写盘, 不绑 ContextVar (调用方决定)。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.observability.journal_doc import JournalMetadata
from lca.contracts.models.observability.journal_step import AttachmentRef
from lca.infrastructure.observability.writable_matrix.coordinator import (
    StepCoordinator,
)
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)

__all__ = [
    "BuildJournalMetadata",
    "build_step_coordinator",
]


@dataclass(frozen=True)
class BuildJournalMetadata:
    """``build_step_coordinator`` 用的结构化 metadata 输入。

    字段语义对齐 :class:`JournalMetadata`。 transport 层把
    ``RunSession`` 拆成这个 dataclass, 再交给 runtime, 避免 ``runtime``
    反向 import transport。
    """

    agent_role: str
    strategy_key: str
    objective: str
    plan_ref: str = ""
    attachments: tuple[AttachmentRef, ...] = field(default_factory=tuple)
    started_at: float = 0.0


def build_step_coordinator(
    *,
    registry: WritableFaceRegistry,
    run_id: str,
    trace_id: str,
    metadata: BuildJournalMetadata,
) -> StepCoordinator:
    """造一个已 ``bind_run`` 的 coordinator。最窄形态,所有字段由调用方决定。

    返回的 coordinator 已绑定 run, 可以直接调 ``begin_step`` /
    ``record_*`` / ``end_step``。 spine ``<run_id>.spine.jsonl`` 落盘由
    :class:`RoutingFileSink` (registry 中 storage face) 负责。
    journal.json 落盘由 :class:`StepTreeAccumulatorDeriver`
    (subscribed to spine) 负责。
    """
    coord = StepCoordinator(registry=registry, run_id=run_id)
    coord.bind_run(
        run_id=run_id,
        trace_id=trace_id,
        metadata=_to_journal_metadata(metadata),
        started_at=metadata.started_at if metadata.started_at > 0 else None,
    )
    return coord


def _to_journal_metadata(metadata: BuildJournalMetadata) -> JournalMetadata:
    """把结构化输入转 ``JournalMetadata``。 集中唯一构造点,避免散落。"""
    return JournalMetadata(
        agent_role=metadata.agent_role,
        strategy_key=metadata.strategy_key,
        plan_ref=metadata.plan_ref,
        objective=metadata.objective,
        attachments=metadata.attachments,
        outcome="in_progress",
        started_at=metadata.started_at,
        closed_at=None,
        total_steps=0,
    )
