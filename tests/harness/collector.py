"""In-memory Observability collector for tests (not part of lca package)."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability
from lca.layer0_infra.observability.console_observability import ConsoleObservability


@dataclass
class TraceBundle:
    """Collected spans for one or more runs."""

    spans: list[TraceSpan] = field(default_factory=list)

    def by_name(self, name: str) -> list[TraceSpan]:
        return [s for s in self.spans if s.name == name]

    def names(self) -> list[str]:
        return [s.name for s in self.spans]

    def root_spans(self) -> list[TraceSpan]:
        return [s for s in self.spans if s.parent_span_id is None]

    def children(self, span: TraceSpan) -> list[TraceSpan]:
        return [s for s in self.spans if s.parent_span_id == span.span_id]

    def walk(self, span: TraceSpan) -> list[TraceSpan]:
        out = [span]
        for child in self.children(span):
            out.extend(self.walk(child))
        return out

    def has_path_to(self, root_name: str, leaf_name_prefix: str) -> bool:
        for root in self.by_name(root_name):
            for node in self.walk(root):
                if node.name == leaf_name_prefix or node.name.startswith(leaf_name_prefix):
                    return True
        return False

    def shared_trace_ids(self) -> set[str]:
        return {s.trace_id for s in self.spans if s.trace_id}


class InMemoryObservability(Observability):
    """Collect every TraceSpan in memory for topology assertions."""

    name = "in_memory"

    def __init__(self) -> None:
        self.spans: list[TraceSpan] = []

    def emit_span(self, span: TraceSpan) -> None:
        self.spans.append(span)

    def bundle(self) -> TraceBundle:
        return TraceBundle(spans=list(self.spans))

    def clear(self) -> None:
        self.spans.clear()


class LiveCollector(InMemoryObservability):
    """Memory + framework ConsoleObservability (same narrative as real apps)."""

    name = "live_collector"

    def __init__(self, *, live: bool = True, detail: object = None) -> None:
        # detail kept for CLI API compat; console always full-span human view
        del detail
        super().__init__()
        self._console = ConsoleObservability() if live else None

    def emit_span(self, span: TraceSpan) -> None:
        if self._console is not None:
            self._console.emit_span(span)
        super().emit_span(span)
