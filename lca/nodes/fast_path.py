"""ADR-0246 zero-LLM fast-path take counters for loop node executors.

todo-28 C1: per-visit latency is already covered interpreter-side by
``NodeLatencyTracker`` (``d9295dda7``: count/total/min/max/p50/p95 per
node_id at all visit_end paths). What was still missing is the fast-path
coverage — how many visits took the explicit zero-cost shortcut that skips
the expensive work (LLM/brain call, envelope minting). This mixin counts
exactly that; call :meth:`note_fast_path` on the shortcut's early-return
branch. Coverage = ``fast_path_count()`` / tracker count for the node.

Additive only: no behavior change, the sole runtime delta is one counter
increment on the shortcut branch.

Frozen-dataclass note: the executors are ``@dataclass(frozen=True,
slots=True)``. The counter lives in a slot declared on this mixin
(inherited by the recreated dataclass) and is written with
``object.__setattr__``, initialized in ``__post_init__`` (invoked by the
dataclass-generated ``__init__``). Domain state stays frozen — only this
one slot is ever written, and only by the methods below.
"""

from __future__ import annotations


class FastPathCounter:
    """Count visits that took the explicit zero-cost fast-path shortcut."""

    __slots__ = ("_fast_path_count",)

    def __post_init__(self) -> None:
        # Invoked by the dataclass-generated __init__ of the executor.
        # object.__setattr__ bypasses the frozen __setattr__ for this
        # observability-only slot; domain fields remain effectively frozen.
        object.__setattr__(self, "_fast_path_count", 0)

    def note_fast_path(self) -> None:
        """Mark the current visit as having taken the zero-cost shortcut.

        Call this on the early-return branch that skips the expensive work
        (LLM/brain call, envelope minting) — the ADR-0246 "zero-LLM" /
        ADR-0244 PR-3 "zero-cost" fast path.
        """
        object.__setattr__(self, "_fast_path_count", self._fast_path_count + 1)

    def fast_path_count(self) -> int:
        """Number of visits that took the fast-path shortcut so far."""
        return self._fast_path_count

    def reset_fast_path_count(self) -> None:
        """Zero the counter; starts a fresh observation window."""
        object.__setattr__(self, "_fast_path_count", 0)
