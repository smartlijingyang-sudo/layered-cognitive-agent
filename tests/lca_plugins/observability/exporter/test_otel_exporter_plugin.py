"""observability.exporter.otel pilot plugin tests (ADR-0195 P2-19)."""

from __future__ import annotations

from lca.harness.plugin.declaration import definition_from_plugin
from lca.plugins.observability.exporter.otel import plugin as otel_plugin


def test_otel_exporter_plugin_manifest() -> None:
    definition = definition_from_plugin(otel_plugin.setup, module=__name__)
    assert definition.id == "observability.exporter.otel"
    assert "exporter.otel" in tuple(definition.provided_capability_keys)


def test_otel_exporter_noop_without_tracer() -> None:
    exporter = otel_plugin.OtelExporter()
    exporter.export_document({"schema": "lca.journal/3.1", "steps": ()})


def test_otel_exporter_bind_tracer() -> None:
    exporter = otel_plugin.OtelExporter()

    class _Tracer:
        pass

    tracer = _Tracer()
    exporter.bind_tracer(tracer)
    assert exporter._tracer is tracer
