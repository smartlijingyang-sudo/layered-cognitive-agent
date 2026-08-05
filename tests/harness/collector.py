"""In-memory observability collectors for tests (not part of lca package).

新基建：collector 本身就是 ``ObservabilityHub``（内置 OTel InMemoryExporter），
直接作为 observability 注入；``TraceBundle`` 查询 API 不变（SpanView 投影）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.layer0_infra.observability import ObservabilityHub, SpanView
from lca.layer0_infra.observability.journal.console_projector import ConsoleJournalProjector
from lca.layer0_infra.observability.view import view_of


@dataclass
class TraceBundle:
    """Collected spans for one or more runs."""

    spans: list[SpanView] = field(default_factory=list)

    def by_name(self, name: str) -> list[SpanView]:
        return [s for s in self.spans if s.name == name]

    def names(self) -> list[str]:
        return [s.name for s in self.spans]

    def root_spans(self) -> list[SpanView]:
        return [s for s in self.spans if s.parent_span_id is None]

    def children(self, span: SpanView) -> list[SpanView]:
        return [s for s in self.spans if s.parent_span_id == span.span_id]

    def walk(self, span: SpanView) -> list[SpanView]:
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


class InMemoryObservability(ObservabilityHub):
    """Collect every span in memory for topology assertions (injectable hub)."""

    name = "in_memory"

    def __init__(self) -> None:
        self._memory_exporter = InMemorySpanExporter()
        super().__init__([self._memory_exporter])

    def bundle(self) -> TraceBundle:
        self.flush()
        views = [view_of(s) for s in self._memory_exporter.get_finished_spans()]
        return TraceBundle(spans=views)

    def clear(self) -> None:
        self._memory_exporter.clear()


class LiveCollector(InMemoryObservability):
    """Memory + journal console projector (same narrative as real apps)."""

    name = "live_collector"

    def __init__(self, *, live: bool = True, detail: object = None) -> None:
        # detail kept for CLI API compat; console = journal-driven human view
        del detail
        self._memory_exporter = InMemorySpanExporter()
        projectors = [ConsoleJournalProjector()] if live else []
        ObservabilityHub.__init__(self, [self._memory_exporter], journal_projectors=projectors)
