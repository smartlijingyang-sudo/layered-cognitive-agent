"""OTel exporter plugin package (ADR-0195 P2-19)."""

from lca.plugins.observability.exporter.otel.plugin import OtelExporter, setup

__all__ = ["OtelExporter", "setup"]
