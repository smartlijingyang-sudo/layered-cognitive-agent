"""Tool-batch execution policy registry — PR-3 (G-19, ADR-0232) default.

The Body boundary schedules a model-emitted tool batch through a
``ToolBatchExecutionPolicy``.  Pre-PR-3 the default was
``SequentialToolBatchExecutionPolicy``; PR-3 promotes
``ParallelReadOnlyToolBatchPolicy`` to default because the run-time
profile of LCA calls is dominated by read-only invocations
(``runCommand`` / ``profile_diff`` / ``profile_apply``) where the
60–80ms inter-call gap was pure serial latency (B-3).

The new policy is deliberately conservative:

- PARALLEL iff every entry declares ``effects == "read"`` AND every
  entry's grant carries the ``concurrent`` sub-key (C5 monotonic).
- SEQUENTIAL otherwise — preserving pre-PR-3 behaviour for any
  write / external / un-audited batch.

The pre-existing ``ParallelToolBatchExecutionPolicy`` /
``SequentialToolBatchExecutionPolicy`` / ``SafeToolBatchExecutionPolicy``
classes are kept for callers that explicitly opt in (bundles, tests).
This module exposes the new default + a factory that the Body picks up
when no policy is supplied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.protocols.act.tool.batch_execution import (
    ToolBatchEntry,
    ToolBatchExecutionMode,
    ToolBatchExecutionPolicy,
)


@dataclass(frozen=True, slots=True)
class ReadOnlyToolBatchEntry:
    """Bundle-side facts a policy needs to gate the parallel default.

    ``ToolBatchEntry`` (protocol-level) carries only ``call_id`` /
    ``tool_name`` / ``is_idempotent``.  PR-3 adds an audit channel:
    the Body passes the per-entry ``effects`` value (resolved via the
    tool registry, see ``lca/contracts/cognition/body/tools/registry.py``)
    plus the resolved ``CapabilityGrant`` map so the policy can check
    the ``concurrent`` sub-key without re-querying either store.
    """

    call_id: str
    tool_name: str
    effects: str  # "read" | "write" | "external"
    grant: Mapping[str, object]


class ParallelReadOnlyToolBatchPolicy(ToolBatchExecutionPolicy):
    """PARALLEL iff every entry is read-only AND has ``grant.concurrent``.

    Mixed batches (any ``"write"`` / ``"external"``) fall back to
    SEQUENTIAL because the cost of partial-batch rollback on an
    interleaved write side-effect is far higher than the latency win
    from overlap.  The check on ``grant.concurrent`` keeps C5
    monotonic intact: a Body constructed without the concurrent grant
    is by definition a caller who has not been authorised to overlap
    tools, so the policy refuses to parallelise even if every entry is
    read-only.
    """

    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        # The protocol-level entries tuple does not carry effects /
        # grant metadata.  The Body constructs an enriched view via
        # ``select_mode_with_audit`` and dispatches through that
        # overload; this Protocol method is the no-audit fallback that
        # preserves back-compat for any caller still passing the
        # bare tuple.
        return ToolBatchExecutionMode.SEQUENTIAL

    def select_mode_with_audit(
        self, audited: tuple[ReadOnlyToolBatchEntry, ...]
    ) -> ToolBatchExecutionMode:
        if not audited:
            return ToolBatchExecutionMode.SEQUENTIAL
        if all(
            entry.effects == "read" and bool(entry.grant.get("concurrent"))
            for entry in audited
        ):
            return ToolBatchExecutionMode.PARALLEL
        return ToolBatchExecutionMode.SEQUENTIAL


def default_tool_batch_policy() -> ToolBatchExecutionPolicy:
    """Factory used by ``ToolBatchExecutor.__init__`` when no policy is supplied.

    Kept as a function (not a module constant) so a future profile
    knob can swap the default without touching import sites.  PR-3
    intentionally does not expose a profile knob (ADR-0232 §Decision 4
    — no rollback flag); the factory return value is therefore
    unconditionally the parallel-read-only policy.
    """

    return ParallelReadOnlyToolBatchPolicy()


__all__ = [
    "ParallelReadOnlyToolBatchPolicy",
    "ReadOnlyToolBatchEntry",
    "default_tool_batch_policy",
]
