"""JournalDocument —— run 顶层 envelope (ADR-0164 草案)。

对比 v2 envelope(``lca.journal/2`` schema):
    - 顶层从 ``{schema, run_seq, descriptor, data, ...}`` 改为
      ``{schema, run_id, trace_id, started_at, steps: [...], metadata}``
    - 不再有 ``run_seq`` —— seq 是 step 内部实现, 不暴露顶层
    - 不再有 ``_doc`` / ``_redaction`` boilerplate —— metadata 收口
    - 顶层 ``steps`` 是有序 tuple, 不再追加流

``JournalDocument`` 是 ``traces/runs/<run_id>/journal.json`` 的根结构,
projector 在 run 终止时一次性写出(不再流式追加)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.observability.journal_step import (
    AttachmentRef,
    JournalStep,
)

JournalSchemaVersion = Literal["lca.journal/3"]


@dataclass(frozen=True)
class JournalMetadata:
    """run 级元信息, 跨 step 不变。

    - ``objective``: 顶层 objective, 跟第一个 step 的
      ``context_before.objective`` 保持一致(便于 reader 不用下钻)。
    - ``attachments``: 顶层附件, 同上。
    - ``outcome``: run 最终 outcome, 在 close 时由 terminalizer 写入。
    """

    agent_role: str
    strategy_key: str
    plan_ref: str
    objective: str
    attachments: tuple[AttachmentRef, ...] = ()
    outcome: Literal["completed", "failed", "paused", "stopped", "in_progress"] = "in_progress"
    started_at: float = 0.0
    closed_at: float | None = None
    total_steps: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JournalDocument:
    """run 顶层 envelope, step 序列 + 元信息。

    主存储格式: ``traces/runs/<run_id>/journal.json``(pretty-printed JSON)。
    不再使用 NDJSON 流式追加 —— 顶层真相是 step 树, 由 projector 在 run
    终止时一次性写出。
    """

    schema: JournalSchemaVersion
    run_id: RunId
    trace_id: TraceId
    started_at: float
    steps: tuple[JournalStep, ...]
    metadata: JournalMetadata
    closed_at: float | None = None

    def total_steps(self) -> int:
        """返回 step 总数(跟 metadata.total_steps 一致, 但不依赖 metadata 落盘)。"""
        return len(self.steps)

    def step_by_index(self, step_index: int) -> JournalStep | None:
        """O(1) 查找 step_index 对应的 step(假设 step_index 顺序, 实际 O(n))。

        返回 None 表示越界。 reader 友好。
        """
        for step in self.steps:
            if step.step_index == step_index:
                return step
        return None

    def step_by_id(self, step_id: str) -> JournalStep | None:
        """按 step_id 查找(O(n), 但 reader 调用不频繁)。"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def prior_summary_chain(self) -> tuple[str, ...]:
        """从所有已闭合 step 拼接反思摘要链。

        用于 step 上下联系 —— reader 调一次拿完整因果链, 不用遍历。
        """
        from lca.contracts.models.observability.journal_step import (
            summarize_step,
        )

        return tuple(summarize_step(s) for s in self.steps if s.outcome is not None)

    def cumulative_files(self) -> tuple[str, ...]:
        """截至本 run 末尾, 所有 step.tool_result.files_created 累加去重。

        reader 友好。
        """
        seen: list[str] = []
        for step in self.steps:
            if step.tool_result is None:
                continue
            for f in step.tool_result.files_created:
                if f not in seen:
                    seen.append(f)
        return tuple(seen)


def empty_document(
    *,
    run_id: RunId,
    trace_id: TraceId,
    metadata: JournalMetadata,
    started_at: float,
) -> JournalDocument:
    """构造空 document —— 起步时调用, 之后 append_step。"""
    return JournalDocument(
        schema="lca.journal/3",
        run_id=run_id,
        trace_id=trace_id,
        started_at=started_at,
        steps=(),
        metadata=metadata,
    )


def append_step(
    doc: JournalDocument,
    step: JournalStep,
) -> JournalDocument:
    """不可变 append —— 返回新 document, 旧 document 不变。

    runtime 在 close_step 时调用。
    """
    new_steps = (*doc.steps, step)
    new_meta = JournalMetadata(
        agent_role=doc.metadata.agent_role,
        strategy_key=doc.metadata.strategy_key,
        plan_ref=doc.metadata.plan_ref,
        objective=doc.metadata.objective,
        attachments=doc.metadata.attachments,
        outcome=doc.metadata.outcome,
        started_at=doc.metadata.started_at,
        closed_at=doc.metadata.closed_at,
        total_steps=len(new_steps),
        extra=doc.metadata.extra,
    )
    return JournalDocument(
        schema=doc.schema,
        run_id=doc.run_id,
        trace_id=doc.trace_id,
        started_at=doc.started_at,
        steps=new_steps,
        metadata=new_meta,
        closed_at=doc.closed_at,
    )


def close_document(
    doc: JournalDocument,
    *,
    outcome: Literal["completed", "failed", "paused", "stopped"],
    closed_at: float,
) -> JournalDocument:
    """标记 run 终止。"""
    new_meta = JournalMetadata(
        agent_role=doc.metadata.agent_role,
        strategy_key=doc.metadata.strategy_key,
        plan_ref=doc.metadata.plan_ref,
        objective=doc.metadata.objective,
        attachments=doc.metadata.attachments,
        outcome=outcome,
        started_at=doc.metadata.started_at,
        closed_at=closed_at,
        total_steps=len(doc.steps),
        extra=doc.metadata.extra,
    )
    return JournalDocument(
        schema=doc.schema,
        run_id=doc.run_id,
        trace_id=doc.trace_id,
        started_at=doc.started_at,
        steps=doc.steps,
        metadata=new_meta,
        closed_at=closed_at,
    )


__all__ = [
    "JournalDocument",
    "JournalMetadata",
    "JournalSchemaVersion",
    "append_step",
    "close_document",
    "empty_document",
]
