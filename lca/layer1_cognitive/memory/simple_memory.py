"""四类记忆的最小实现：内存列表存储 + 简单相关性检索 + 可选团队共享。"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    META_ROLE,
    META_STEP,
    META_SUBTASK,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
)
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import MemorySystem, SharedMemoryStore

_DEFAULT_MAX_WORKING = 20
_DEFAULT_MAX_EPISODIC = 50


class SimpleMemorySystem(MemorySystem):
    """Working / Semantic / Episodic / Procedural 四层记忆。

    可选绑定 SharedMemoryStore：对声明共享的层（semantic/procedural），
    读写直接走共享 store，实现跨 Agent 记忆共享；未声明共享的层保持私有。
    """

    def __init__(self, shared_store: SharedMemoryStore | None = None) -> None:
        self._shared_store: SharedMemoryStore | None = shared_store
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
        records: list[MemoryRecord] = []
        for layer_name in self._private_layers:
            records.extend(self._get_layer_records(layer_name))
        state.retrieved_context = records
        return state

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        # 追加到 working memory 而非覆盖，确保多步委派历史对 agent 可见
        for record in self._working_records_for(state, observation):
            self._private_layers[MemoryLayer.WORKING].append(record)
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

        Delegation results become one attributed record per member instead of a
        ``TOOL_RESULT:`` blob, so the lead can see *who answered what*.
        Tool results keep the ``TOOL_RESULT:`` prefix (mock-LLM parses it).
        Failed observations are recorded as ``TOOL_ERROR:`` so the LLM can see
        what went wrong and correct its next action (ReAct observation channel).
        """
        if observation.payload is None and observation.success:
            return []
        kind = observation.extra.get(OBS_RESULT_KIND, MemoryRecordKind.GENERIC)
        # 委派结果：失败但可能带 partial 证据，仍走类型化写入（ADR-0049）
        if kind == MemoryRecordKind.DELEGATION_RESULT:
            return self._delegation_records(state, observation)
        if not observation.success:
            error_detail = observation.error or "unknown error"
            partial = observation.payload
            content = f"TOOL_ERROR: {error_detail}"
            if isinstance(partial, str) and partial.strip():
                content = f"{content}\nPARTIAL: {partial}"
            return [
                MemoryRecord(
                    record_id=new_id("mem"),
                    content=content,
                    memory_type=MemoryLayer.WORKING,
                    importance=0.9,
                    source_trace_id=state.trace_id,
                    kind=MemoryRecordKind.GENERIC,
                    metadata={META_STEP: state.step},
                )
            ]
        if kind == MemoryRecordKind.RESPONSE:
            content = f"MY_RESPONSE: {observation.payload}"
        elif kind == MemoryRecordKind.TOOL_RESULT:
            content = f"TOOL_RESULT: {observation.payload}"
        else:
            content = f"TOOL_RESULT: {observation.payload}"
        return [
            MemoryRecord(
                record_id=new_id("mem"),
                content=content,
                memory_type=MemoryLayer.WORKING,
                importance=0.9,
                source_trace_id=state.trace_id,
                kind=kind,
                metadata={META_STEP: state.step},
            )
        ]

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
