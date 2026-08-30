"""Temporal memory system for LCA's standard cognitive lifecycle."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord, MemoryRelationKind, MemoryTrust
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import MemorySystem, TemporalMemoryStore
from lca.infrastructure.state_store.sqlite_temporal_memory import SqliteTemporalMemoryStore
from lca.cognition.memory.policy import (
    MemoryAuthority,
    MemoryPolicy,
    MemoryWrite,
    SimpleMemoryPolicy,
)

_DEFAULT_SCOPE = "local:default"
_DEFAULT_RECALL_LIMIT = 8
_ARCHIVE_CONFIDENCE = 0.75


class TemporalMemorySystem(MemorySystem):
    """Query-aware temporal memory backed by a durable ``TemporalMemoryStore``.

    Every result rendered into a model turn is marked ``UNTRUSTED_HISTORY``.
    This preserves the distinction between an auditable memory fact and a
    model-visible historical reference: memory can inform a decision but may
    never function as a policy, permission or current user instruction.
    """

    def __init__(
        self,
        *,
        store: TemporalMemoryStore | None = None,
        db_path: str | Path = ".lca/temporal-memory.sqlite3",
        scope_id: str = _DEFAULT_SCOPE,
        recall_limit: int = _DEFAULT_RECALL_LIMIT,
        policy: MemoryPolicy | None = None,
        **_: object,
    ) -> None:
        if recall_limit < 1:
            raise ValueError("recall_limit must be positive")
        self._store = store or SqliteTemporalMemoryStore(db_path)
        self._scope_id = scope_id.strip() or _DEFAULT_SCOPE
        self._recall_limit = recall_limit
        self._policy = policy or SimpleMemoryPolicy()

    @property
    def store(self) -> TemporalMemoryStore:
        """Expose the storage seam for controlled revision and diagnostics."""
        return self._store

    async def perceive(self, state: AgentState) -> AgentState:
        """Recall scoped, currently-valid facts before Think without mutating state."""
        query = self._query_for(state)
        if not query:
            return replace(state, retrieved_context=[])
        as_of_ms = state.extra.get("memory_as_of_ms")
        if not isinstance(as_of_ms, int):
            as_of_ms = None
        scoped_records = self._store.recall(
            scope_id=self._scope_for(state),
            query=query,
            as_of_ms=as_of_ms,
            limit=self._recall_limit,
        )
        evidence = [
            replace(
                record,
                trust=MemoryTrust.UNTRUSTED_HISTORY,
                metadata={**record.metadata, "recall_query": query},
            )
            for record in scoped_records
        ]
        return replace(state, retrieved_context=evidence)

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        """Archive a concise Reflect outcome through the standard MemoryPolicy gate."""
        content = self._archive_content(state, observation, reflection)
        write = MemoryWrite(
            record_id=new_id("temporal"),
            layer=MemoryLayer.EPISODIC,
            authority=MemoryAuthority.MODEL_INFERENCE,
            content=content,
            confidence=_ARCHIVE_CONFIDENCE,
            source_event_refs=(
                state.trace_id,
                observation.observation_id,
                reflection.reflection_id,
            ),
            kind=MemoryRecordKind.GENERIC,
            metadata={
                "source": "automatic_turn_archive",
                "step": state.step,
                "observation_success": observation.success,
                "reflection_verdict": reflection.verdict.value,
            },
        )
        result = self._policy.commit((write,))
        for record in result.accepted:
            self._store.remember(
                replace(
                    record,
                    scope_id=self._scope_for(state),
                    source_trace_id=state.trace_id,
                    provenance="memory.update",
                    trust=MemoryTrust.TRUSTED,
                )
            )

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        """Return current records of one memory layer in this system's scope."""
        return [
            record
            for record in self._store.list_records(scope_id=self._scope_id)
            if record.memory_type is layer
        ]

    def remember(
        self,
        *,
        content: str,
        layer: MemoryLayer = MemoryLayer.SEMANTIC,
        importance: float = 0.8,
        provenance: str = "user_confirmed",
        confidence: float | None = 1.0,
        scope_id: str | None = None,
        valid_from_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Append an explicitly admitted fact for callers with write authority."""
        return self._store.remember(
            MemoryRecord(
                record_id=new_id("temporal"),
                content=content,
                memory_type=layer,
                importance=importance,
                provenance=provenance,
                confidence=confidence,
                scope_id=scope_id or self._scope_id,
                valid_from_ms=valid_from_ms,
                metadata=dict(metadata or {}),
            )
        )

    def revise(
        self,
        record_id: str,
        *,
        content: str,
        reason: str = "revised",
        importance: float = 0.8,
        provenance: str = "user_confirmed",
    ) -> MemoryRecord:
        """Soft-supersede a prior fact and retain its historical time interval."""
        replacement = MemoryRecord(
            record_id=new_id("temporal"),
            content=content,
            memory_type=MemoryLayer.SEMANTIC,
            importance=importance,
            provenance=provenance,
            confidence=1.0,
            scope_id=self._scope_id,
        )
        return self._store.revise(record_id, replacement, reason=reason)

    def retire(self, record_id: str, *, reason: str = "retired") -> None:
        """Soft-retire a fact without removing it from audit history."""
        self._store.retire(record_id, reason=reason)

    def relate(self, source_id: str, target_id: str, relation: MemoryRelationKind) -> None:
        """Create an explicit relationship between persisted memory facts."""
        self._store.relate(source_id, target_id, relation)

    def close(self) -> None:
        self._store.close()

    def _scope_for(self, state: AgentState) -> str:
        scope = state.extra.get("memory_scope_id")
        return scope.strip() if isinstance(scope, str) and scope.strip() else self._scope_id

    @staticmethod
    def _query_for(state: AgentState) -> str:
        explicit = state.extra.get("memory_query")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        return state.task.strip()

    @staticmethod
    def _archive_content(
        state: AgentState, observation: Observation, reflection: Reflection
    ) -> str:
        parts = [
            f"task={state.task}",
            f"step={state.step}",
            f"success={observation.success}",
            f"verdict={reflection.verdict.value}",
        ]
        if reflection.lesson:
            parts.append(f"lesson={reflection.lesson}")
        if observation.error:
            parts.append(f"error={observation.error}")
        return " | ".join(parts)


__all__ = ["TemporalMemorySystem"]
