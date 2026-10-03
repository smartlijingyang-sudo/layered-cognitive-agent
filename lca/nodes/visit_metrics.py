"""Per-visit latency + fast-path observability for loop node executors.

todo-28 C1: the reflect/remember nodes must answer "how much latency tax do
blocking reflect+remember add per turn?" and "what is the ADR-0246 zero-LLM
fast-path coverage?". This mixin is the reflect/remember counterpart of the
per-gate counters added to ``ChainedDecisionGate`` (``162594acb``).

Additive only: mix it into an executor, rename its ``node_execute`` body to
``_node_execute``, and keep a thin timing wrapper under the protocol name.
Visit behavior is unchanged; the only runtime delta is ``perf_counter``
bookkeeping. Counters are cumulative over the executor instance's lifetime
(plugin ``setup()`` provides a single instance per node); call
:meth:`reset_visit_stats` to start a fresh observation window. Per-step
durable verdicts remain the phase ``*.checked`` / ``*.served`` evidence
descriptors declared in each node's plugin contract.

Frozen-dataclass note: the six executors are
``@dataclass(frozen=True, slots=True)``. The counters live in slots declared
on this mixin (inherited by the recreated dataclass) and are written with
``object.__setattr__``, initialized in ``__post_init__`` (invoked by the
dataclass-generated ``__init__``). Domain state stays frozen — only the
three metrics slots are ever written, and only by the metrics methods below.
"""

from __future__ import annotations


class VisitMetricsMixin:
    """Record per-visit wall latency and explicit fast-path takes."""

    __slots__ = ("_visit_count", "_visit_total_ms", "_fast_path_count")

    def __post_init__(self) -> None:
        # Invoked by the dataclass-generated __init__ of the executor.
        # object.__setattr__ bypasses the frozen __setattr__ for these
        # observability-only slots; domain fields remain effectively frozen.
        object.__setattr__(self, "_visit_count", 0)
        object.__setattr__(self, "_visit_total_ms", 0.0)
        object.__setattr__(self, "_fast_path_count", 0)

    def record_visit(self, elapsed_ms: float) -> None:
        """Record one completed visit of ``node_execute`` (success or error)."""
        object.__setattr__(self, "_visit_count", self._visit_count + 1)
        object.__setattr__(self, "_visit_total_ms", self._visit_total_ms + elapsed_ms)

    def note_fast_path(self) -> None:
        """Mark the current visit as having taken the explicit zero-cost shortcut.

        Call this on the early-return branch that skips the expensive work
        (LLM/brain call, envelope minting) — the ADR-0246 "zero-LLM" /
        ADR-0244 PR-3 "zero-cost" fast path.
        """
        object.__setattr__(self, "_fast_path_count", self._fast_path_count + 1)

    def visit_stats(self) -> dict[str, int | float]:
        """Snapshot of visit counters (a fresh dict on every call)."""
        return {
            "visits": self._visit_count,
            "total_ms": self._visit_total_ms,
            "fast_path_visits": self._fast_path_count,
        }

    def reset_visit_stats(self) -> None:
        """Zero all counters; starts a fresh observation window."""
        object.__setattr__(self, "_visit_count", 0)
        object.__setattr__(self, "_visit_total_ms", 0.0)
        object.__setattr__(self, "_fast_path_count", 0)
