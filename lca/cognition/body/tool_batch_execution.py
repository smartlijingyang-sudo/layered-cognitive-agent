"""Built-in scheduling strategies for a model-emitted tool batch.

The strategies are deliberately pure. They decide only whether already
validated calls may overlap; ``SafeExecutor`` continues to own every tool's
permission checks, retries, idempotency, audit receipt, and world effect.
"""

from __future__ import annotations

from lca.contracts.protocols.tool_batch_execution import (
    ToolBatchEntry,
    ToolBatchExecutionMode,
    ToolBatchExecutionPolicy,
    ToolBatchExecutionSegment,
    ToolBatchSegmentPlanningPolicy,
)


class ParallelToolBatchExecutionPolicy(ToolBatchExecutionPolicy):
    """Run every multi-tool batch concurrently after the normal safety gates."""

    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        del entries
        return ToolBatchExecutionMode.PARALLEL


class SequentialToolBatchExecutionPolicy(ToolBatchExecutionPolicy):
    """Preserve model-declared order for every multi-tool batch."""

    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        del entries
        return ToolBatchExecutionMode.SEQUENTIAL


class SafeToolBatchExecutionPolicy(ToolBatchExecutionPolicy):
    """Parallelize only batches containing exclusively idempotent tools.

    A non-idempotent call can mutate files, devices, or remote services. The
    conservative default therefore preserves declared order whenever any call
    may have a non-repeatable effect, while retaining parallel latency for
    read-only/idempotent batches.
    """

    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        if all(entry.is_idempotent for entry in entries):
            return ToolBatchExecutionMode.PARALLEL
        return ToolBatchExecutionMode.SEQUENTIAL


class SegmentedSafeToolBatchExecutionPolicy(
    SafeToolBatchExecutionPolicy, ToolBatchSegmentPlanningPolicy
):
    """Preserve side-effect barriers while parallelizing safe contiguous runs.

    Hermes uses this scheduling shape for a mixed model-emitted tool batch: it
    executes maximal contiguous groups that are safe to overlap and keeps an
    interactive, unknown, or side-effecting call as a sequential barrier. In
    LCA the policy is intentionally narrower: the already-declared
    ``is_idempotent`` fact is its only input. It cannot inspect arguments,
    authorize tools, or invoke them directly.
    """

    def select_segments(
        self, entries: tuple[ToolBatchEntry, ...]
    ) -> tuple[ToolBatchExecutionSegment, ...]:
        if not entries:
            return ()

        segments: list[ToolBatchExecutionSegment] = []
        start = 0
        while start < len(entries):
            entry = entries[start]
            if not entry.is_idempotent:
                segments.append(
                    ToolBatchExecutionSegment(
                        start=start,
                        stop=start + 1,
                        mode=ToolBatchExecutionMode.SEQUENTIAL,
                    )
                )
                start += 1
                continue

            stop = start + 1
            while stop < len(entries) and entries[stop].is_idempotent:
                stop += 1
            segments.append(
                ToolBatchExecutionSegment(
                    start=start,
                    stop=stop,
                    mode=ToolBatchExecutionMode.PARALLEL,
                )
            )
            start = stop

        return tuple(segments)


__all__ = [
    "ParallelToolBatchExecutionPolicy",
    "SafeToolBatchExecutionPolicy",
    "SegmentedSafeToolBatchExecutionPolicy",
    "SequentialToolBatchExecutionPolicy",
]
