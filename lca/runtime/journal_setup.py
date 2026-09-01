"""Runtime factory that arms a ``StepLifecycleStore`` for one run.

ADR-0164 Phase 7 端到端: 之前 ``lca/plugins/seams/observability/run_ledger.py``
的 ``create_run_components`` 通过 ContextVar 拿 lifecycle store,但
production 代码从未 ``set_lifecycle_store`` —— 导致 ``StepGroupedBackend``
永远是 None, ``journal.json`` 从未被落盘。

本模块把 "为某个 run 准备 lifecycle store" 显式化成 runtime 工厂,
不依赖任何 transport 类型:

- ``build_step_lifecycle_store`` —— 给定 run_id / trace_id / metadata,
  直接造一个 ``StepLifecycleStore`` 并 ``bind_run``。 是最窄的形态。

不在本模块做的事:
    - 不负责 set ContextVar —— 调用方决定是否需要 ContextVar 路径
      (legacy 单元测试 + facade API 仍依赖 ContextVar)。
    - 不负责落盘 —— ``StepGroupedBackend.flush`` 是 sink,
      ``StepLifecycleStore.close_and_finalize`` 是 source, 本模块只负责
      source 端的构造。
    - 不依赖 transport —— 调用方从 ``RunSession`` 推导 metadata 后传入
      ``BuildJournalMetadata``(保持 ``runtime → transport`` 单向)。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.observability.journal_doc import JournalMetadata
from lca.contracts.models.observability.journal_step import AttachmentRef
from lca.runtime.step_lifecycle import StepLifecycleStore

__all__ = [
    "BuildJournalMetadata",
    "build_step_lifecycle_store",
]


@dataclass(frozen=True)
class BuildJournalMetadata:
    """``build_step_lifecycle_store`` 用的结构化 metadata 输入。

    字段语义对齐 :class:`JournalMetadata`。 transport 层把
    ``RunSession`` 拆成这个 dataclass,再交给 runtime,避免 ``runtime``
    反向 import transport。
    """

    agent_role: str
    strategy_key: str
    objective: str
    plan_ref: str = ""
    attachments: tuple[AttachmentRef, ...] = field(default_factory=tuple)
    started_at: float = 0.0


def build_step_lifecycle_store(
    *,
    run_id: str,
    trace_id: str,
    metadata: BuildJournalMetadata,
) -> StepLifecycleStore:
    """造一个已 ``bind_run`` 的 store。 最窄形态,所有字段由调用方决定。

    返回的 store 已绑定 run,可以直接调 ``open_step`` / ``record_*`` /
    ``close_step``。 落盘是 ``StepGroupedBackend`` 的事,本函数不碰。
    """
    store = StepLifecycleStore()
    store.bind_run(
        run_id=run_id,
        trace_id=trace_id,
        metadata=_to_journal_metadata(metadata),
        started_at=metadata.started_at if metadata.started_at > 0 else None,
    )
    return store


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
