"""SpineContext — ContextVar-based per-task scope.

Phase machine guarantees I13: span push/pop EP-mismatch raises.
Sequence/epoch are run-scoped monotonic counters.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


class PhaseMachineViolationError(Exception):
    """I13 — end ep without matching start ep."""


# Back-compat alias: keep the original name to avoid breaking
# external ``except PhaseMachineViolation`` callers (chore: ruff N818).
PhaseMachineViolation = PhaseMachineViolationError


@dataclass(frozen=True, slots=True)
class SpanContext:
    execution_point: str
    span_id: str
    parent_span_id: str | None


class SpineContext:
    """Context-local Spine state. All classmethods; no instance."""

    _run_id: ContextVar[str | None] = ContextVar("lca_spine_run_id", default=None)
    _step_id: ContextVar[str | None] = ContextVar("lca_spine_step_id", default=None)
    _span_stack: ContextVar[tuple[SpanContext, ...]] = ContextVar(
        "lca_spine_span_stack", default=()
    )
    _seq: ContextVar[int] = ContextVar("lca_spine_seq", default=0)
    _epoch: ContextVar[int] = ContextVar("lca_spine_epoch", default=0)
    _span_counter: ContextVar[int] = ContextVar("lca_spine_span_counter", default=0)
    _hash_chain: ContextVar[str | None] = ContextVar("lca_spine_prev_hash", default=None)

    # ── run / step ─────────────────────────────────────────────────────
    @classmethod
    def set_run(cls, run_id: str) -> None:
        cls._run_id.set(run_id)

    @classmethod
    def get_run(cls) -> str | None:
        return cls._run_id.get()

    @classmethod
    def set_step(cls, step_id: str) -> None:
        cls._step_id.set(step_id)

    @classmethod
    def get_step(cls) -> str | None:
        return cls._step_id.get()

    # ── monotonic counters ─────────────────────────────────────────────
    @classmethod
    def next_sequence(cls) -> int:
        val = cls._seq.get() + 1
        cls._seq.set(val)
        return val

    @classmethod
    def next_epoch(cls) -> int:
        val = cls._epoch.get() + 1
        cls._epoch.set(val)
        return val

    @classmethod
    def last_hash(cls) -> str | None:
        return cls._hash_chain.get()

    @classmethod
    def chain_hash(cls, new_hash: str | None) -> None:
        cls._hash_chain.set(new_hash)

    # ── span stack ─────────────────────────────────────────────────────
    @classmethod
    def push_span(cls, execution_point: str) -> SpanContext:
        parent_id = cls._span_stack.get()[-1].span_id if cls._span_stack.get() else None
        counter = cls._span_counter.get() + 1
        cls._span_counter.set(counter)
        span = SpanContext(
            execution_point=execution_point,
            span_id=f"lca-span-{counter:08x}",
            parent_span_id=parent_id,
        )
        cls._span_stack.set((*cls._span_stack.get(), span))
        return span

    @classmethod
    def pop_span(cls, execution_point: str) -> SpanContext:
        stack = cls._span_stack.get()
        if not stack:
            raise PhaseMachineViolation(f"pop_span({execution_point!r}) on empty stack")
        top = stack[-1]
        if top.execution_point != execution_point:
            raise PhaseMachineViolation(
                f"end {execution_point!r} without matching start {top.execution_point!r}"
            )
        cls._span_stack.set(stack[:-1])
        return top

    @classmethod
    def current_span(cls) -> SpanContext | None:
        stack = cls._span_stack.get()
        return stack[-1] if stack else None

    @classmethod
    def span_stack_depth(cls) -> int:
        return len(cls._span_stack.get())
