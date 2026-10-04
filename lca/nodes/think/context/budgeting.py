"""Shared byte-budget policy and context plumbing for ``think.context.*`` nodes.

PR-B split the old ``think.context.compact`` into single-responsibility
nodes; the byte-accounting policy (soft gate at 0.7, settle target at
0.5, tail-keeping truncation) and the runtime-carrier resolvers are
shared by ``truncate`` (byte cut) and ``summarize`` (sediment-first,
ADR-0283). One definition, imported by both — not duplicated per node.

Policy (unchanged from the original single node):
- soft gate at ``COMPACTION_THRESHOLD_RATIO`` (0.7 of ``max_tokens``);
  below it nodes emit ``noop`` receipts;
- settle target at ``TARGET_AFTER_RATIO`` (0.5 of ``max_tokens``) so the
  next turn has headroom before re-entering compaction.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext

# Soft compaction threshold: only compact once the working context has
# grown past this fraction of the token budget. Below it the node emits a
# ``noop`` receipt. The hard "budget exceeded → terminate" check is the
# separate ``think.budget.gate`` node.
COMPACTION_THRESHOLD_RATIO: float = 0.7
# Conservative target: leave the working payload at ~50% of max_tokens after
# compaction so the next turn has headroom before re-entering the node.
TARGET_AFTER_RATIO: float = 0.5


def should_compact(budget: Budget) -> bool:
    """Soft compaction gate: ``used_tokens`` past ``COMPACTION_THRESHOLD_RATIO``.

    ``max_tokens`` unset / non-positive ⇒ no compaction (a step-bounded run
    keeps a ``noop`` receipt so downstream stays deterministic).
    """
    if budget.max_tokens is None or budget.max_tokens <= 0:
        return False
    return budget.used_tokens >= COMPACTION_THRESHOLD_RATIO * budget.max_tokens


def payload_byte_size(payload: tuple[Any, ...]) -> int:
    """Byte size of the payload as projected to the LLM wire.

    Each element is rendered with :func:`repr` and the lengths are
    summed. Precise token accounting lives elsewhere — this is the
    deterministic, dependency-free estimate the nodes use to decide
    when the target byte budget has been met.
    """
    return sum(len(repr(item)) for item in payload)


def truncate_oldest_to_byte_budget(
    payload: tuple[Any, ...], *, target_bytes: int
) -> tuple[Any, ...]:
    """Keep the tail (most recent) of ``payload`` until it fits ``target_bytes``.

    Empty payload is a no-op. ``target_bytes <= 0`` collapses to the
    empty tuple — the caller must ensure ``max_tokens > 0`` before
    invoking compaction (the upstream ``think.budget.gate`` enforces
    that the run continues only when the budget has remaining room).
    """
    if not payload:
        return payload
    if target_bytes <= 0:
        return ()
    kept: list[Any] = []
    running = 0
    for item in reversed(payload):
        size = len(repr(item))
        if running + size > target_bytes and kept:
            break
        kept.append(item)
        running += size
    kept.reverse()
    return tuple(kept)


def _resolve_state(*, context: NodeContext) -> object:
    """Pull ``state`` from the whitelisted runtime carrier.

    Runtime-carrier read; matches the convention used by
    ``think.budget.gate`` and ``think.decision.repair``.
    """
    runtime = getattr(context, "runtime", None)
    state_obj = getattr(runtime, "state", None) if runtime is not None else None
    if state_obj is None and runtime is not None and hasattr(runtime, "get"):
        state_obj = runtime.get("state")
    return state_obj


def resolve_budget(*, context: NodeContext) -> Budget:
    """Pull ``Budget`` from ``state.budget`` via the runtime carrier."""
    state_obj = _resolve_state(context=context)
    budget = getattr(state_obj, "budget", None) if state_obj is not None else None
    if isinstance(budget, Budget):
        return budget
    raise TypeError(
        "think.context.* expects state.budget via the runtime carrier; got "
        f"{type(budget).__name__ if budget is not None else 'None'}"
    )


def resolve_context_payload(*, context: NodeContext) -> tuple[Any, ...]:
    """Return the retrieved_context payload as an immutable tuple.

    Behavior-preserving fallback to ``state.retrieved_context`` (the
    same source the prior single ``context.compact`` node read).
    """
    state_obj = _resolve_state(context=context)
    value = (
        getattr(state_obj, "retrieved_context", None)
        if state_obj is not None
        else None
    )
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


__all__ = [
    "COMPACTION_THRESHOLD_RATIO",
    "TARGET_AFTER_RATIO",
    "payload_byte_size",
    "resolve_budget",
    "resolve_context_payload",
    "should_compact",
    "truncate_oldest_to_byte_budget",
]
