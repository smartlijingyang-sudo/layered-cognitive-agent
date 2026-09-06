"""Prepared memory journal facts (ADR-0194 P1-13).

Cognition memory prepares :class:`MemoryJournalReceipt` / :class:`MemorySpineReceipt`;
loop layer commits via ``FactGateway`` (spine EP) or journal append seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from lca.contracts.models.observability.journal import (
    ContextCompacted,
    JournalEvent,
    MemoryCommitted,
)


@dataclass(frozen=True, slots=True)
class MemoryJournalReceipt:
    """One prepared legacy journal catalog fact ready for loop commit."""

    journal_event: JournalEvent
    actor: str = "memory"


@dataclass(frozen=True, slots=True)
class MemorySpineReceipt:
    """One prepared memory spine EP ready for ``publish_ep_bound``."""

    ep: Literal["memory.read", "memory.write"]
    payload: dict[str, Any]
    actor: str = "memory"


def memory_read_spine_receipt(*, state_id: str, outcome: str = "success") -> MemorySpineReceipt:
    """Build a ``memory.read`` spine receipt."""
    return MemorySpineReceipt(
        ep="memory.read",
        payload={"state_id": state_id, "outcome": outcome},
    )


def memory_write_spine_receipt(
    *,
    state_id: str,
    layer: str,
    record_id: str | None = None,
    outcome: str = "success",
) -> MemorySpineReceipt:
    """Build a ``memory.write`` spine receipt."""
    payload: dict[str, Any] = {
        "state_id": state_id,
        "layer": layer,
        "outcome": outcome,
    }
    if record_id is not None:
        payload["record_id"] = record_id
    return MemorySpineReceipt(ep="memory.write", payload=payload)


def context_compacted_receipt(
    *,
    step: int,
    original_kinds: tuple[str, ...],
    kept_kinds: tuple[str, ...],
    mode: str = "selection",
    applied: bool = False,
    reason: str = "selection_only",
    source_record_count: int = 0,
    summary_record_id: str = "",
    original_characters: int = 0,
    result_characters: int = 0,
    compression_ratio: float = 0.0,
    coverage_ratio: float = 0.0,
) -> MemoryJournalReceipt:
    """Build a ``ContextCompacted`` journal receipt from compaction output."""
    return MemoryJournalReceipt(
        journal_event=ContextCompacted(
            step=step,
            original_kinds=original_kinds,
            kept_kinds=kept_kinds,
            mode=mode,
            applied=applied,
            reason=reason,
            source_record_count=source_record_count,
            summary_record_id=summary_record_id,
            original_characters=original_characters,
            result_characters=result_characters,
            compression_ratio=compression_ratio,
            coverage_ratio=coverage_ratio,
        ),
    )


def memory_committed_receipt(
    *,
    layer: str,
    record_id: str,
    record_kind: str = "",
) -> MemoryJournalReceipt:
    """Build a ``MemoryCommitted`` journal receipt."""
    return MemoryJournalReceipt(
        journal_event=MemoryCommitted(
            layer=layer,
            record_id=record_id,
            record_kind=record_kind,
        ),
    )


__all__ = [
    "MemoryJournalReceipt",
    "MemorySpineReceipt",
    "context_compacted_receipt",
    "memory_committed_receipt",
    "memory_read_spine_receipt",
    "memory_write_spine_receipt",
]
