"""四类记忆的最小实现：内存列表存储 + 简单相关性检索 + 可选团队共享。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

# v3 §8 / PR7.D.6/7: the system is wired
from lca.cognition.memory.null.retrieval_policy import NullRetrievalPolicy
from lca.cognition.memory.policy.policy import (
    CompactionPolicy,
    MemoryCommitResult,
    MemoryPolicy,
    MemoryWrite,
    SimpleCompactionPolicy,
    SimpleMemoryPolicy,
)
from lca.cognition.memory.semantic.compaction import CompactionReport
from lca.contracts.atoms.enums.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    META_ROLE,
    META_STEP,
    META_SUBTASK,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
)
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.memory.journal_receipt import (
    MemoryJournalReceipt,
    context_compacted_receipt,
    memory_committed_receipt,
    memory_read_spine_receipt,
    memory_write_spine_receipt,
)
from lca.contracts.protocols import MemorySystem, RetrievalPolicy, SharedMemoryStore

_DEFAULT_MAX_WORKING = 20
_DEFAULT_MAX_EPISODIC = 50


def _record_kind_value(record: MemoryRecord) -> str:
    kind = record.kind
    return kind.value if hasattr(kind, "value") else str(kind)


def _layer_value(layer: MemoryLayer) -> str:
    return layer.value if hasattr(layer, "value") else str(layer)


def _context_compacted_from_report(
    *,
    step: int,
    original_kinds: tuple[str, ...],
    kept_kinds: tuple[str, ...],
    report: CompactionReport | None,
) -> MemoryJournalReceipt:
    if report is None:
        return context_compacted_receipt(
            step=step,
            original_kinds=original_kinds,
            kept_kinds=kept_kinds,
        )
    return context_compacted_receipt(
        step=step,
        original_kinds=original_kinds,
        kept_kinds=kept_kinds,
        mode=report.mode,
        applied=report.applied,
        reason=report.reason,
        source_record_count=len(report.source_record_ids),
        summary_record_id=report.summary_record_id or "",
        original_characters=report.original_characters,
        result_characters=report.result_characters,
        compression_ratio=report.compression_ratio,
        coverage_ratio=report.coverage_ratio,
    )


class SimpleMemorySystem(MemorySystem):
    """Working / Semantic / Episodic / Procedural 四层记忆。

    可选绑定 SharedMemoryStore：对声明共享的层（semantic/procedural），
    读写直接走共享 store，实现跨 Agent 记忆共享；未声明共享的层保持私有。

    v3 §8 / PR7.D.6/7：
    - 写入必经 ``MemoryPolicy.commit(writes)``；返回 ``MemoryCommitResult``；
      接受部分 emit ``MemoryCommitted``，拒绝部分 emit ``MemoryWriteRejected``。
    - ``perceive`` 末尾影子调用 ``CompactionPolicy.compact``；emit ``ContextCompacted``。
    """

    def __init__(
        self,
        shared_store: SharedMemoryStore | None = None,
        *,
        policy: MemoryPolicy | None = None,
        compaction: CompactionPolicy | None = None,
        retrieval: RetrievalPolicy | None = None,
    ) -> None:
        self._shared_store: SharedMemoryStore | None = shared_store
        # Public attrs so tests / hot-reload can swap in custom policies
        # via ``system.policy = ...`` (PR7.D.6/7).
        self.policy: MemoryPolicy = policy or SimpleMemoryPolicy()
        self.compaction: CompactionPolicy = compaction or SimpleCompactionPolicy()
        self.retrieval: RetrievalPolicy = retrieval or NullRetrievalPolicy()
        self._private_layers: dict[MemoryLayer, list[MemoryRecord]] = {
            MemoryLayer.WORKING: [],
            MemoryLayer.SEMANTIC: [],
            MemoryLayer.EPISODIC: [],
            MemoryLayer.PROCEDURAL: [],
        }

    def _get_layer_records(self, layer: MemoryLayer) -> list[MemoryRecord]:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            return self._shared_store.get_records(layer)
        return self._private_layers[layer]

    def _append_record(self, layer: MemoryLayer, record: MemoryRecord) -> None:
        if self._shared_store is not None and self._shared_store.is_shared(layer):
            self._shared_store.add_record(layer, record)
        else:
            self._private_layers[layer].append(record)

    async def perceive(self, state: AgentState) -> AgentState:
        """Return a context-enriched state value without mutating the input instance."""
        from lca.loop.commit.memory_journal import (
            commit_memory_journal_receipt,
            commit_memory_spine_receipt,
        )

        commit_memory_spine_receipt(
            memory_read_spine_receipt(state_id=state.trace_id),
            state=state,
        )
        # PR7.D.7: fold each layer's records; emit ContextCompacted with
        # original vs kept kinds.  Empty compaction is still journaled
        # (every Perceive gets an audit trail).
        layers_snapshot: dict[MemoryLayer, list[MemoryRecord]] = {
            layer_name: self._get_layer_records(layer_name) for layer_name in self._private_layers
        }
        # ADR-0068: RetrievalPolicy is the 4-layer weighted selection seam.
        # Default NullRetrievalPolicy returns ``[]``; standard bundle upgrades
        # to LayeredRetrievalPolicy which preserves WORKING + prioritizes
        # SEMANTIC / PROCEDURAL.
        candidates = self.retrieval.retrieve(layers_snapshot, budget=_DEFAULT_MAX_WORKING)
        # CompactionPolicy applies the final cap on the retrieval selection.
        candidate_view = tuple(candidates)
        compacted = list(self.compaction.compact(candidate_view, budget=_DEFAULT_MAX_WORKING))
        report_method = getattr(self.compaction, "report", None)
        report = (
            report_method(candidate_view, budget=_DEFAULT_MAX_WORKING)
            if callable(report_method)
            else None
        )
        if report is not None and not isinstance(report, CompactionReport):
            raise TypeError("memory compaction report() must return CompactionReport or None")
        kinds = tuple(
            _record_kind_value(record) for records in layers_snapshot.values() for record in records
        )
        kept_kinds = tuple(_record_kind_value(record) for record in compacted)
        commit_memory_journal_receipt(
            _context_compacted_from_report(
                step=state.step,
                original_kinds=kinds,
                kept_kinds=kept_kinds,
                report=report,
            ),
            state=state,
        )
        return replace(state, retrieved_context=compacted)

    def _shadow_compact(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        """保留作为 compact 路径的兼容 helper；ADR-0068 后实际由
        ``CompactionPolicy.compact`` 直接调用。"""
        budget = _DEFAULT_MAX_WORKING
        return list(self.compaction.compact(tuple(records), budget=budget))

    def commit(self, writes: tuple[MemoryWrite, ...]) -> MemoryCommitResult:
        """Apply writes via ``MemoryPolicy``; emit ``MemoryCommitted`` (PR7.D.6).

        Returns ``MemoryCommitResult(accepted, rejected)``.  ``accepted``
        records are appended to their target layers; ``rejected`` writes
        are not stored.  Both sides journal via loop ``memory_journal_commit``.
        """
        from lca.loop.commit.memory_journal import (
            commit_memory_journal_receipt,
            commit_memory_spine_receipt,
        )

        state_id = "memory-system"
        if writes and writes[0].metadata.get("source_trace_id"):
            state_id = str(writes[0].metadata["source_trace_id"])
        result = self.policy.commit(writes)
        for rec in result.accepted:
            self._append_record(rec.memory_type, rec)
        for rec in result.accepted:
            commit_memory_journal_receipt(
                memory_committed_receipt(
                    layer=_layer_value(rec.memory_type),
                    record_id=rec.record_id,
                ),
            )
            commit_memory_spine_receipt(
                memory_write_spine_receipt(
                    state_id=state_id,
                    layer=_layer_value(rec.memory_type),
                    record_id=rec.record_id,
                    outcome="success",
                ),
            )
        for rej in result.rejected:
            commit_memory_journal_receipt(
                memory_committed_receipt(
                    layer=_layer_value(rej.write.layer),
                    record_id=rej.write.record_id,
                    record_kind="rejected",
                ),
            )
            commit_memory_spine_receipt(
                memory_write_spine_receipt(
                    state_id=state_id,
                    layer=_layer_value(rej.write.layer),
                    record_id=rej.write.record_id,
                    outcome="rejected",
                ),
            )
        return result

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        # 追加到 working memory 而非覆盖，确保多步委派历史对 agent 可见
        for rec in self._working_records_for(state, observation):
            self._private_layers[MemoryLayer.WORKING].append(rec)
        # 防止 working memory 无限增长
        if len(self._private_layers[MemoryLayer.WORKING]) > _DEFAULT_MAX_WORKING:
            self._private_layers[MemoryLayer.WORKING] = self._private_layers[MemoryLayer.WORKING][
                -_DEFAULT_MAX_WORKING:
            ]
        episodic_content = (
            f"step={state.step} success={observation.success} verdict={reflection.verdict}"
        )
        if reflection.lesson and not observation.success:
            episodic_content += f" | {reflection.lesson}"
        self._append_record(
            MemoryLayer.EPISODIC,
            MemoryRecord(
                record_id=new_id("mem"),
                content=episodic_content,
                memory_type=MemoryLayer.EPISODIC,
                importance=0.5,
                source_trace_id=state.trace_id,
            ),
        )
        await self.compress()

    def _working_records_for(
        self, state: AgentState, observation: Observation
    ) -> list[MemoryRecord]:
        """Type the observation into working-memory records.

        Delegation results become one attributed record per member.
        Tool I/O never enters working memory — it already lives on the
        provider ``role=tool`` message (LobeHub wire). Episodic still
        stores the short lesson for failures.
        """
        kind = observation.extra.get(OBS_RESULT_KIND, MemoryRecordKind.GENERIC)
        if kind == MemoryRecordKind.DELEGATION_RESULT:
            return self._delegation_records(state, observation)
        if kind == MemoryRecordKind.RESPONSE and observation.payload is not None:
            return [
                MemoryRecord(
                    record_id=new_id("mem"),
                    content=f"MY_RESPONSE: {observation.payload}",
                    memory_type=MemoryLayer.WORKING,
                    importance=0.9,
                    source_trace_id=state.trace_id,
                    kind=kind,
                    metadata={META_STEP: state.step},
                )
            ]
        return []

    def _delegation_records(
        self, state: AgentState, observation: Observation
    ) -> list[MemoryRecord]:
        results = observation.extra.get(OBS_MEMBER_RESULTS)
        if not isinstance(results, dict) or not results:
            return []
        subtasks = observation.extra.get(OBS_MEMBER_SUBTASKS)
        subtasks = subtasks if isinstance(subtasks, dict) else {}
        records: list[MemoryRecord] = []
        for role, output in results.items():
            records.append(
                MemoryRecord(
                    record_id=new_id("mem"),
                    content=str(output) if output is not None else "",
                    memory_type=MemoryLayer.WORKING,
                    importance=0.9,
                    source_trace_id=state.trace_id,
                    kind=MemoryRecordKind.DELEGATION_RESULT,
                    metadata={
                        META_ROLE: str(role),
                        META_SUBTASK: str(subtasks.get(role, "")),
                        META_STEP: state.step,
                    },
                )
            )
        return records

    async def compress(self) -> None:
        episodic = self._get_layer_records(MemoryLayer.EPISODIC)
        if len(episodic) > _DEFAULT_MAX_EPISODIC:
            if self._shared_store is not None and self._shared_store.is_shared(
                MemoryLayer.EPISODIC
            ):
                pass  # episodic 不应被共享，防御性跳过
            else:
                self._private_layers[MemoryLayer.EPISODIC] = episodic[-_DEFAULT_MAX_EPISODIC:]

    def write_shared_record(self, layer: MemoryLayer, record: MemoryRecord) -> None:
        """显式向共享层写入记录（供外部策略/编排代码使用）。"""
        if self._shared_store is None or not self._shared_store.is_shared(layer):
            raise KeyError(f"层 {layer!r} 未配置为共享")
        self._shared_store.add_record(layer, record)

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        """显式查询指定层的记录。共享层走 SharedStore，私有层走本地存储。"""
        return list(self._get_layer_records(layer))

    def get_private_layer_snapshot(self) -> dict[str, Any]:
        """返回私有层的当前状态快照，用于测试和调试。"""
        return {k.value: list(v) for k, v in self._private_layers.items()}
