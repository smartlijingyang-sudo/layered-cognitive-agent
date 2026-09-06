"""Contracts for policy-controlled scheduling of a model turn's tool batch.

A model may emit several tool calls in one decision. The Body remains the only
execution boundary, while a profile-selected policy decides whether calls are
safe to overlap or must retain their declared order. A policy may additionally
expose a segmented plan: the Body executes its contiguous segments in order,
while only each safe segment overlaps. This is a Body strategy seam, not a new
cognitive phase or action type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ToolBatchExecutionMode(StrEnum):
    """The only scheduling modes admitted for already-authorized tool calls."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True, slots=True)
class ToolBatchEntry:
    """The policy-visible, provider-neutral facts for one tool invocation.

    Policies deliberately receive neither the concrete tool object nor mutable
    arguments. Authorization, validation, retries, idempotency, and the actual
    world effect remain owned by the existing SafeExecutor pipeline.
    """

    call_id: str
    tool_name: str
    is_idempotent: bool


@dataclass(frozen=True, slots=True)
class ToolBatchExecutionSegment:
    """One contiguous, half-open range in a model-declared tool batch.

    ``start`` and ``stop`` index the original call order as ``[start, stop)``.
    Segment plans cannot omit, reorder, or duplicate calls: the Body validates
    this before dispatching any world effect.
    """

    start: int
    stop: int
    mode: ToolBatchExecutionMode


@runtime_checkable
class ToolBatchExecutionPolicy(Protocol):
    """Select one scheduling mode for a validated tool batch.

    This stable, single-mode protocol remains the baseline extension point.
    Policies that can safely exploit mixed batches implement the additive
    ``ToolBatchSegmentPlanningPolicy`` protocol below.
    """

    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        """Return the policy-approved execution mode for the supplied batch."""
        ...


@runtime_checkable
class ToolBatchSegmentPlanningPolicy(Protocol):
    """Optional extension for policies that schedule contiguous batch segments.

    The returned sequence must cover every entry once, from index zero to the
    final entry, without overlap. ``validate_tool_batch_execution_segments``
    enforces that invariant at the Body boundary before any dispatch occurs.
    """

    def select_segments(
        self, entries: tuple[ToolBatchEntry, ...]
    ) -> tuple[ToolBatchExecutionSegment, ...]:
        """Return an ordered execution schedule for the supplied batch."""
        ...


def validate_tool_batch_execution_segments(
    segments: tuple[ToolBatchExecutionSegment, ...], *, entry_count: int
) -> None:
    """Reject plans that could skip, duplicate, reorder, or create empty work.

    The validation is deliberately local to the Body boundary. A scheduling
    plugin selects concurrency only; it never obtains permission to alter the
    model-declared invocation set or bypass SafeExecutor for an individual call.
    """

    if entry_count < 1:
        raise ValueError("tool batch segment validation requires at least one entry")
    if not segments:
        raise ValueError("tool batch segment plan must contain at least one segment")

    next_start = 0
    for segment in segments:
        if segment.start != next_start:
            raise ValueError(
                "tool batch segment plan must be contiguous and preserve declared order"
            )
        if segment.stop <= segment.start:
            raise ValueError("tool batch segment plan cannot contain an empty segment")
        if segment.stop > entry_count:
            raise ValueError("tool batch segment plan exceeds the declared batch")
        next_start = segment.stop

    if next_start != entry_count:
        raise ValueError("tool batch segment plan must cover the complete declared batch")


__all__ = [
    "ToolBatchEntry",
    "ToolBatchExecutionMode",
    "ToolBatchExecutionPolicy",
    "ToolBatchExecutionSegment",
    "ToolBatchSegmentPlanningPolicy",
    "validate_tool_batch_execution_segments",
]
