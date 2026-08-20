"""Memory policies — MemoryPolicy + CompactionPolicy (PR7.D.6 / PR7.D.7).

v3 §5.5 splits memory writes into two phases:

1. ``MemoryPolicy.commit(writes) -> MemoryCommitResult`` — authoritatively
   accepts or rejects each ``MemoryWrite``.  The default
   ``SimpleMemoryPolicy`` rejects ``MODEL_INFERENCE`` writes below a
   configurable confidence threshold and accepts every other authority.

2. ``CompactionPolicy.compact(records, budget) -> tuple`` — trims the
   memory view by ``recency_score`` so the Reasoner sees only what fits
   the budget.  The default ``SimpleCompactionPolicy`` is a stable
   top-``budget`` selection.

Both Protocols are pure-function shapes: implementations must NOT carry
state outside what the caller threads in.  The runtime injects them
into ``SimpleMemorySystem`` via constructor; tests can override either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.memory import MemoryRecord


class MemoryAuthority(str, Enum):
    """Origin authority of a memory write (v3 §5.5).

    Drives ``MemoryPolicy`` accept / reject decisions.  Adding new
    authorities is intentionally a deliberate enum change.
    """

    USER_CONFIRMED = "user_confirmed"
    TOOL_OBSERVATION = "tool_observation"
    SYSTEM = "system"
    MODEL_INFERENCE = "model_inference"


@dataclass(frozen=True)
class MemoryWrite:
    """A candidate memory write pending policy evaluation.

    ``source_event_refs`` ties the write back to the journal / observation
    that produced it, for audit + retention later (PR7.D.6).
    """

    record_id: str
    layer: MemoryLayer
    authority: MemoryAuthority
    content: str
    confidence: float = 1.0
    source_event_refs: tuple[str, ...] = field(default_factory=tuple)
    kind: MemoryRecordKind = MemoryRecordKind.GENERIC
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWriteRejected:
    """A write rejected by ``MemoryPolicy``.

    The full ``MemoryWrite`` is preserved so observability surfaces can
    render what was rejected and why.
    """

    write: MemoryWrite
    reason: str


@dataclass(frozen=True)
class MemoryCommitResult:
    """Outcome of ``MemoryPolicy.commit``.

    ``accepted`` is materialized into ``MemoryRecord`` instances (the
    canonical type stored on disk / shared store); ``rejected`` carries
    the original write + reason for audit.
    """

    accepted: tuple[MemoryRecord, ...]
    rejected: tuple[MemoryWriteRejected, ...]


@runtime_checkable
class MemoryPolicy(Protocol):
    """Decide which writes survive a memory commit batch."""

    def commit(self, writes: tuple[MemoryWrite, ...]) -> MemoryCommitResult: ...


@runtime_checkable
class CompactionPolicy(Protocol):
    """Trim a memory view down to ``budget`` records (by recency)."""

    def compact(
        self,
        records: tuple[MemoryRecord, ...],
        budget: int,
    ) -> tuple[MemoryRecord, ...]: ...


_DEFAULT_MIN_CONFIDENCE = 0.5


class SimpleMemoryPolicy(MemoryPolicy):
    """Default authority-based policy.

    - ``USER_CONFIRMED``, ``TOOL_OBSERVATION``, ``SYSTEM`` → always accepted.
    - ``MODEL_INFERENCE`` → accepted when ``confidence >= min_confidence``;
      otherwise rejected with reason ``"confidence_below_threshold"``.

    The threshold is intentionally low (0.5) to keep the default permissive;
    production overrides (e.g. tighter on ``episodic``) should subclass.
    """

    def __init__(self, *, min_confidence: float = _DEFAULT_MIN_CONFIDENCE) -> None:
        self._min_confidence = min_confidence

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    def commit(self, writes: tuple[MemoryWrite, ...]) -> MemoryCommitResult:
        accepted: list[MemoryRecord] = []
        rejected: list[MemoryWriteRejected] = []
        for write in writes:
            if self._accept(write):
                accepted.append(self._materialize(write))
            else:
                rejected.append(
                    MemoryWriteRejected(
                        write=write,
                        reason="confidence_below_threshold",
                    )
                )
        return MemoryCommitResult(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
        )

    def _accept(self, write: MemoryWrite) -> bool:
        if write.authority is not MemoryAuthority.MODEL_INFERENCE:
            return True
        return write.confidence >= self._min_confidence

    @staticmethod
    def _materialize(write: MemoryWrite) -> MemoryRecord:
        return MemoryRecord(
            record_id=write.record_id,
            content=write.content,
            memory_type=write.layer,
            importance=write.confidence,
            recency_score=write.confidence,
            source_trace_id=None,
            metadata={
                "authority": write.authority.value,
                "source_event_refs": list(write.source_event_refs),
                **dict(write.metadata),
            },
            kind=write.kind,
        )


class SimpleCompactionPolicy(CompactionPolicy):
    """Stable top-``budget`` selection by ``recency_score``.

    Records with no ``recency_score`` are treated as 0.0.  When the input
    fits in ``budget`` the result is the input verbatim (preserving order).
    """

    def compact(
        self,
        records: tuple[MemoryRecord, ...],
        budget: int,
    ) -> tuple[MemoryRecord, ...]:
        if budget <= 0 or len(records) <= budget:
            return records
        # Sort ascending by recency_score; None recency treated as -inf
        # so the records with the highest score survive the budget cut.
        scored = sorted(
            records,
            key=lambda r: (
                r.recency_score is not None,
                r.recency_score if r.recency_score is not None else 0.0,
            ),
        )
        kept = scored[-budget:]
        ids = {r.record_id for r in kept}
        return tuple(r for r in records if r.record_id in ids)


__all__ = [
    "CompactionPolicy",
    "MemoryAuthority",
    "MemoryCommitResult",
    "MemoryPolicy",
    "MemoryWrite",
    "MemoryWriteRejected",
    "SimpleCompactionPolicy",
    "SimpleMemoryPolicy",
]


# Quiet re-export for callers that want to materialize records.
new_memory_record = new_id  # re-export so tests can pin record_id
