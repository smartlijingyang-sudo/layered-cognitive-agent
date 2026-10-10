"""Contracts for policy-controlled scheduling of a model turn's tool batch.

A model may emit several tool calls in one decision. The Body remains the only
execution boundary, while a profile-selected policy decides whether calls are
safe to overlap or must retain their declared order. A policy may also
expose a segmented plan: the Body executes its contiguous segments in order,
while only each safe segment overlaps. This is a Body strategy seam, not a new
cognitive phase or action type.
"""

from __future__ import annotations

from collections.abc import Mapping
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
class ReadOnlyToolBatchEntry:
    """Bundle-side facts a policy needs to gate the parallel default.

    ``ToolBatchEntry`` (protocol-level) carries only ``call_id`` /
    ``tool_name`` / ``is_idempotent``.  PR-3 (ADR-0232) adds an audit
    channel: the Body passes the per-entry ``effects`` value (resolved
    via the tool registry,
    see ``lca/contracts/cognition/body/tools/registry.py``) plus the
    resolved capability-grant map so the policy can check the
    ``concurrent`` sub-key without re-querying either store.

    Moved here from ``lca.cognition.body.tools.execution_policy`` (RA-087):
    the audit channel's facts type is part of the policy contract, and
    contracts must not import from cognition.
    """

    call_id: str
    tool_name: str
    effects: str  # "read" | "write" | "external"
    grant: Mapping[str, object]


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


@runtime_checkable
class AuditAwareToolBatchPolicy(Protocol):
    """Additive extension for policies that gate on per-entry audit facts.

    A policy declares the audit channel by implementing
    ``select_mode_with_audit``; the Body then enriches each
    ``ToolBatchEntry`` into a ``ReadOnlyToolBatchEntry`` (resolved
    ``effects`` + capability grant) and dispatches through this overload.

    Policies implementing only the base ``ToolBatchExecutionPolicy``
    have no audit channel: the Body never enriches entries for them
    and defers to the protocol-level ``select_mode``.  That fallback is
    explicit and documented on the Body side — never a silent
    enrich-and-ignore.
    """

    def select_mode_with_audit(
        self, audited: tuple[ReadOnlyToolBatchEntry, ...]
    ) -> ToolBatchExecutionMode:
        """Return the policy-approved mode for the audit-enriched batch."""
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
    "AuditAwareToolBatchPolicy",
    "ReadOnlyToolBatchEntry",
    "ToolBatchEntry",
    "ToolBatchExecutionMode",
    "ToolBatchExecutionPolicy",
    "ToolBatchExecutionSegment",
    "ToolBatchSegmentPlanningPolicy",
    "validate_tool_batch_execution_segments",
]
