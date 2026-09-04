# COMPAT(delete-when: ADR-0186 PR-3g graph fold 替代 callback deriver,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# graph 用 on_event 累积 execution_point 边 → phase_graph.dot；生产路径
# 未硬 subscribe（仅 capability）。收口时改为 SpineReader snapshot fold
# 出 edge list，再删本 mutable 累积器。

"""GraphDeriver — accumulate execution-point edges into a Graphviz digraph.

Minimal spine deriver: ``on_event`` records consecutive ``execution_point``
transitions in memory; ``flush`` (or a terminal-ish event) writes a
``phase_graph.dot`` file. Per FD-2, ``on_event`` never raises.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)

_DEFAULT_OUTPUT = Path(".lca/spine/phase_graph.dot")

# Terminal-ish execution points that trigger an automatic flush.
_TERMINAL_POINTS: frozenset[str] = frozenset(
    {
        "kernel.run.stop",
        "kernel.run.cancelled",
    }
)


class GraphDeriver(Deriver):
    """In-memory execution-point edge accumulator → Graphviz digraph.

    Parameters
    ----------
    output_path:
        Destination for ``phase_graph.dot``. Defaults to
        ``.lca/spine/phase_graph.dot``.
    """

    def __init__(self, output_path: str | Path | None = None) -> None:
        self._output_path = Path(output_path) if output_path else _DEFAULT_OUTPUT
        self._edges: list[tuple[str, str]] = []
        self._nodes: set[str] = set()
        self._prev_point: str | None = None

    @property
    def output_path(self) -> Path:
        """Configured digraph output path."""
        return self._output_path

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Observed consecutive execution-point edges (test seam)."""
        return list(self._edges)

    def on_event(self, event: EventRecord) -> None:
        """Record an edge from the previous execution_point to this one.

        Never raises (FD-2). On terminal-ish points, attempts an
        automatic flush to ``output_path``.
        """
        try:
            point = event.execution_point
            self._nodes.add(point)
            if self._prev_point is not None and self._prev_point != point:
                self._edges.append((self._prev_point, point))
            self._prev_point = point
            if point in _TERMINAL_POINTS:
                self.flush()
        except Exception as exc:
            log.warning(
                "graph_deriver.on_event failed execution_point=%s err=%s",
                getattr(event, "execution_point", "?"),
                exc,
                exc_info=True,
            )

    def flush(self, path: str | Path | None = None) -> Path:
        """Write a minimal Graphviz ``digraph`` to ``path`` (or configured path).

        Creates parent directories as needed. Returns the written path.
        """
        dest = Path(path) if path is not None else self._output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        lines = ["digraph phase_graph {"]
        for node in sorted(self._nodes):
            lines.append(f'  "{_escape(node)}";')
        for src, dst in self._edges:
            lines.append(f'  "{_escape(src)}" -> "{_escape(dst)}";')
        lines.append("}")
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.debug("graph_deriver.flush wrote path=%s edges=%d", dest, len(self._edges))
        return dest


def _escape(label: str) -> str:
    """Escape double quotes for Graphviz node/edge labels."""
    return label.replace("\\", "\\\\").replace('"', '\\"')


__all__ = ["GraphDeriver"]
