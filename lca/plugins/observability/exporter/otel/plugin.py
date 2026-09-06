"""observability.exporter.otel — OTel export pilot (ADR-0195 §2.3).

Bridges folded journal / step-tree projections to an injected OTel tracer.
Default profiles omit the delegate; audit / cross-service tracing enables it
via bundle patch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.journal.otel.projector import OtelProjector


@dataclass
class OtelExporter:
    """Export-side OTel bridge; ``bind_tracer`` wires the assemble-time delegate."""

    _tracer: Any = field(default=None, repr=False)

    def bind_tracer(self, tracer: Any) -> None:
        self._tracer = tracer

    def export_document(self, document: Any) -> None:
        """Project one :class:`JournalDocument` (or compatible) via OTel spans."""
        if self._tracer is None:
            return
        OtelProjector(self._tracer, genai_mapper_registry=None).project(document)


@plugin(
    id="observability.exporter.otel",
    provides=("exporter.otel",),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="network",
    description="OTel exporter — projects journal/step-tree DTOs via OtelProjector.",
    test_suite="tests.lca_plugins.observability.exporter.test_otel_exporter_plugin",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("exporter.otel", OtelExporter())


__all__ = ["OtelExporter", "setup"]
