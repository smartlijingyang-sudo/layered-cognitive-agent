"""In-memory observability collectors for tests (not part of lca package).

新基建：collector 直接持有 ``BoundObservability``（内置 OTel InMemoryExporter），
直接作为 observability 注入；``TraceBundle`` 查询 API 不变（SpanView 投影）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.layer0_infra.observability import AttributePolicy, BoundObservability, SpanView
from lca.layer0_infra.observability.tracer_backend import OtelTracer
from lca.layer0_infra.observability.view import view_of
from tests.support.observability_helpers import make_test_bound


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


class InMemoryObservability(BoundObservability):
    """In-memory BoundObservability: collect every span for topology assertions.

    Inherits BoundObservability so ``isinstance(..., BoundObservability)`` succeeds
    and downstream code (spawn_agent, driver) can use it directly. Stores the
    underlying ``InMemorySpanExporter`` so tests can inspect collected spans.
    """

    name = "in_memory"

    def __init__(self) -> None:
        self._memory_exporter = InMemorySpanExporter()
        self._provider = TracerProvider()
        self._provider.add_span_processor(SimpleSpanProcessor(self._memory_exporter))
        raw_tracer = self._provider.get_tracer("test")
        bound = make_test_bound(
            tracer=OtelTracer(raw_tracer, policy=AttributePolicy()),
            otel_tracer=raw_tracer,
        )
        # Frozen dataclass → use object.__setattr__ to initialise fields
        object.__setattr__(self, "journal", bound.journal)
        object.__setattr__(self, "tracer", bound.tracer)
        object.__setattr__(self, "policy", bound.policy)
        object.__setattr__(self, "scorers", bound.scorers)

    def bundle(self) -> TraceBundle:
        self.flush()
        views = [view_of(s) for s in self._memory_exporter.get_finished_spans()]
        return TraceBundle(spans=views)

    def clear(self) -> None:
        self._memory_exporter.clear()

    @property
    def store(self) -> RunStore:
        """Backward compat (§11 pre-existing tests): expose RunStore via .store.

        The _RunStoreBackend has its own .store property that returns
        the underlying RunStore, which has an .events property. We chain:
        collector.store → journal.store → RunStore.events.
        """
        return self.journal.store


class LiveCollector(InMemoryObservability):
    """Memory + journal console projector (same narrative as real apps)."""

    name = "live_collector"

    def __init__(self, *, live: bool = True, detail: object = None) -> None:
        # detail kept for CLI API compat; console = journal-driven human view
        del detail
        from lca.layer0_infra.observability.journal.console_projector import (
            ConsoleJournalProjector,
        )

        self._memory_exporter = InMemorySpanExporter()
        self._provider = TracerProvider()
        self._provider.add_span_processor(SimpleSpanProcessor(self._memory_exporter))
        raw_tracer = self._provider.get_tracer("test")
        projections = [ConsoleJournalProjector()] if live else []
        bound = make_test_bound(
            tracer=OtelTracer(raw_tracer, policy=AttributePolicy()),
            projections=tuple(projections),
            otel_tracer=raw_tracer,
        )
        object.__setattr__(self, "journal", bound.journal)
        object.__setattr__(self, "tracer", bound.tracer)
        object.__setattr__(self, "policy", bound.policy)
        object.__setattr__(self, "scorers", bound.scorers)
