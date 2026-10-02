"""Per-visit node latency tracker — metric surface for todo-28 C1.

The graph interpreter already measures per-visit ``elapsed_ms`` for its
``visit_end`` observations. This module keeps the same samples in-process
so a run (or a contract test) can answer "how much latency tax did each
node pay" without parsing the spine event stream.

Additive observability only: recording never changes execution.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NodeLatencyStats:
    """Aggregate of one node's per-visit latencies (all in milliseconds)."""

    count: int
    total_ms: int
    min_ms: int
    max_ms: int
    p50_ms: float
    p95_ms: float


def _percentile(sorted_samples: list[int], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    rank = (len(sorted_samples) - 1) * pct / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(sorted_samples) - 1)
    frac = rank - lo
    return sorted_samples[lo] * (1.0 - frac) + sorted_samples[hi] * frac


class NodeLatencyTracker:
    """Records per-node visit latencies; :meth:`snapshot` aggregates them.

    Samples are bounded (a deque per node) so long runs cannot grow
    memory without bound. Percentiles are computed over the retained
    window; count/total/min/max reflect the same window.
    """

    def __init__(self, max_samples: int = 4096) -> None:
        self._max_samples = max_samples
        self._samples: dict[str, deque[int]] = {}

    def record(self, node_id: str, elapsed_ms: int) -> None:
        """Record one visit of ``node_id`` taking ``elapsed_ms`` milliseconds."""
        samples = self._samples.get(node_id)
        if samples is None:
            samples = self._samples[node_id] = deque(maxlen=self._max_samples)
        samples.append(max(0, int(elapsed_ms)))

    def snapshot(self) -> dict[str, NodeLatencyStats]:
        """Per-node aggregates over retained samples (deep copies, safe to keep)."""
        out: dict[str, NodeLatencyStats] = {}
        for node_id, samples in self._samples.items():
            ordered = sorted(samples)
            out[node_id] = NodeLatencyStats(
                count=len(ordered),
                total_ms=sum(ordered),
                min_ms=ordered[0] if ordered else 0,
                max_ms=ordered[-1] if ordered else 0,
                p50_ms=_percentile(ordered, 50),
                p95_ms=_percentile(ordered, 95),
            )
        return out

    def reset(self) -> None:
        """Drop all retained samples (e.g. open a new measurement window)."""
        self._samples.clear()
