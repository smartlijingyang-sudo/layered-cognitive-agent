"""Tests for the ``spine.core`` L2 composer plugin (Task 8.1).

The plugin is the single boot DAG node that owns ``EventSpine``
construction (ADR-0165 / ADR-0165.1 §7.6.1). It resolves the L1
``emit_pipeline`` and the L0 ``file_sink`` capabilities, wires them
into one ``EventSpine``, and publishes the holder as the
``event_spine`` capability alongside the ``SpineContext`` class.

These tests pin the documented surface:

- ``id`` / ``layer`` / ``provides`` / ``requires`` match the spec table
- the holder exposes the EventSpine, the FileSink, and the pipeline
- ``close`` defers to ``EventSpine.close``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.base import EventSink

# ── helpers ──────────────────────────────────────────────────────────


class _CountingProducer:
    """Minimal FieldProducer that records ``produce`` invocations."""

    def __init__(self, *, name: str = "stub", priority: int = 100) -> None:
        self.name = name
        self.priority = priority
        self.enabled = True
        self.calls = 0

    def produce(
        self,
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: str,
    ) -> dict[str, Any]:
        del fn, args, kwargs, ctx, span, phase
        self.calls += 1
        return {"stub_field": self.calls}


class _CaptureSink:
    """In-memory ``EventSink`` that records every ``EventRecord`` in order."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []
        self.closed = False

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        self.closed = True


class _StubPluginContext:
    """Stand-in for the audited PluginContext used in plugin tests.

    The class satisfies the same ``provide`` / ``require`` surface that
    ``lca.harness.plugin_api.PluginContext`` exposes, so the spine.core
    ``setup`` runs end-to-end without booting the Cordis carrier. It
    also captures every ``provide`` call so tests can assert what the
    plugin published.
    """

    def __init__(
        self,
        *,
        emit_pipeline: Any,
        file_sink: EventSink,
        optional: dict[str, Any] | None = None,
    ) -> None:
        self._capabilities: dict[str, Any] = {
            "emit_pipeline": emit_pipeline,
            "file_sink": file_sink,
            **(optional or {}),
        }
        self.provided: dict[str, Any] = {}

    def require(self, key: str) -> Any:
        if key not in self._capabilities:
            raise KeyError(f"missing capability {key!r}")
        return self._capabilities[key]

    def soft_get(self, key: str) -> Any | None:
        return self._capabilities.get(key)

    def provide(self, key: str, value: object, **kwargs: object) -> None:
        del kwargs
        self.provided[key] = value

    def register(self, seam: str, name: str, value: object, **kwargs: object) -> None:
        del seam, name, value, kwargs


@pytest.fixture(autouse=True)
def _isolated_spine_context() -> Any:
    """Give every test a clean run-scoped spine state."""
    SpineContext.set_run("spine-core-test")
    SpineContext._span_stack.set(())
    SpineContext._seq.set(0)
    SpineContext._epoch.set(0)
    SpineContext._span_counter.set(0)
    SpineContext._hash_chain.set(None)
    yield
    SpineContext._span_stack.set(())
    SpineContext._hash_chain.set(None)


# ── protocol / metadata ──────────────────────────────────────────────


def test_core_plugin_declares_expected_metadata() -> None:
    """``spine.core`` is an L2 SEAM that emits ``event_spine`` + ``spine_context``."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import core

    assert hasattr(core, "setup")

    definition = definition_from_plugin(core.setup, module=__name__)
    assert definition.id == "spine.core"
    assert definition.spec.layer == "L2"
    assert "event_spine" in definition.provided_capability_keys
    assert "spine_context" in definition.provided_capability_keys
    required = set(definition.required_capability_keys)
    assert "emit_pipeline" in required
    assert "file_sink" in required


def test_module_export_surface() -> None:
    """The module exposes ``SpineCore`` and ``setup`` in its public surface."""
    import lca.plugins.observability.spine.core as core_module

    assert hasattr(core_module, "SpineCore")
    assert hasattr(core_module, "setup")
    assert "SpineCore" in core_module.__all__
    assert "setup" in core_module.__all__


# ── setup wiring ─────────────────────────────────────────────────────


def test_setup_assembles_event_spine_and_publishes_capabilities() -> None:
    """``setup`` resolves L0+L1, builds an ``EventSpine``, publishes both caps."""
    from lca.plugins.observability.spine.core import setup

    producer = _CountingProducer()
    file_sink = _CaptureSink()
    ctx = _StubPluginContext(emit_pipeline=producer, file_sink=file_sink)

    import asyncio

    asyncio.run(setup.setup(ctx, config={}))

    spine_core = ctx.provided["event_spine"]
    spine_context = ctx.provided["spine_context"]

    # SpineContext is published as the class itself so consumers can call
    # ``spine_context.current_span()`` and friends.
    assert spine_context is SpineContext

    # Holder exposes the assembled surface.
    assert isinstance(spine_core.event_spine, EventSpine)
    assert spine_core.file_sink is file_sink
    assert spine_core.emit_pipeline is producer

    # The sink satisfies the EventSink Protocol (structural).
    assert isinstance(spine_core.file_sink, EventSink)


def test_setup_event_spine_routes_through_file_sink(tmp_path: Path) -> None:
    """An event appended through the spine reaches the bound sink."""
    from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
    from lca.plugins.observability.spine.core import setup

    producer = _CountingProducer()
    file_sink = FileSink(tmp_path, run_id="core-wiring")
    ctx = _StubPluginContext(emit_pipeline=producer, file_sink=file_sink)

    import asyncio

    asyncio.run(setup.setup(ctx, config={}))

    spine_core = ctx.provided["event_spine"]
    record = spine_core.event_spine.append(
        execution_point="brain.perceive.start",
        channel="fact",
        caller_payload={"marker": True},
    )
    assert isinstance(record, EventRecord)
    spine_core.close()

    assert (tmp_path / "events.jsonl").exists()
    line = (tmp_path / "events.jsonl").read_text().strip().splitlines()[0]
    assert "brain.perceive.start" in line
    assert file_sink._closed is True


def test_setup_close_defers_to_event_spine_close() -> None:
    """``SpineCore.close`` flushes the bound sink via ``EventSpine.close``."""
    from lca.plugins.observability.spine.core import setup

    producer = _CountingProducer()
    file_sink = _CaptureSink()
    ctx = _StubPluginContext(emit_pipeline=producer, file_sink=file_sink)

    import asyncio

    asyncio.run(setup.setup(ctx, config={}))

    spine_core = ctx.provided["event_spine"]
    spine_core.close()
    assert file_sink.closed is True


def test_setup_requires_emit_pipeline_capability() -> None:
    """Missing ``emit_pipeline`` MUST surface as a KeyError (I4 fail-fast)."""
    from lca.plugins.observability.spine.core import setup

    class _NoPipelineCtx(_StubPluginContext):
        def __init__(self, *, file_sink: EventSink) -> None:
            # Intentionally omit ``emit_pipeline`` from the bag.
            self._capabilities: dict[str, Any] = {"file_sink": file_sink}
            self.provided: dict[str, Any] = {}

        def require(self, key: str) -> Any:
            if key not in self._capabilities:
                raise KeyError(f"missing capability {key!r}")
            return self._capabilities[key]

    ctx = _NoPipelineCtx(file_sink=_CaptureSink())
    import asyncio

    with pytest.raises(KeyError):
        asyncio.run(setup.setup(ctx, config={}))


def test_setup_requires_file_sink_capability() -> None:
    """Missing ``file_sink`` MUST surface as a KeyError (I4 fail-fast)."""
    from lca.plugins.observability.spine.core import setup

    class _NoSinkCtx(_StubPluginContext):
        def __init__(self, *, emit_pipeline: Any) -> None:
            # Intentionally omit ``file_sink`` from the bag.
            self._capabilities: dict[str, Any] = {"emit_pipeline": emit_pipeline}
            self.provided: dict[str, Any] = {}

        def require(self, key: str) -> Any:
            if key not in self._capabilities:
                raise KeyError(f"missing capability {key!r}")
            return self._capabilities[key]

    ctx = _NoSinkCtx(emit_pipeline=_CountingProducer())
    import asyncio

    with pytest.raises(KeyError):
        asyncio.run(setup.setup(ctx, config={}))


def test_setup_soft_subscribes_optional_derivers_and_console_sink() -> None:
    """Optional derivers / console_sink are wired when present; missing is fine."""
    from lca.plugins.observability.spine.core import setup

    class _CountingDeriver:
        def __init__(self) -> None:
            self.calls: list[EventRecord] = []

        def on_event(self, event: EventRecord) -> None:
            self.calls.append(event)

    deriver = _CountingDeriver()
    console = _CaptureSink()
    file_sink = _CaptureSink()
    ctx = _StubPluginContext(
        emit_pipeline=_CountingProducer(),
        file_sink=file_sink,
        optional={"step_tree": deriver, "console_sink": console},
    )

    import asyncio

    asyncio.run(setup.setup(ctx, config={}))

    spine_core = ctx.provided["event_spine"]
    record = spine_core.event_spine.append(
        execution_point="brain.perceive.start",
        channel="fact",
        caller_payload={"marker": True},
    )

    assert len(file_sink.records) == 1
    assert len(console.records) == 1
    assert console.records[0] is record
    assert len(deriver.calls) == 1
    assert deriver.calls[0] is record


# ── SpineCore holder shape ───────────────────────────────────────────


def test_spine_core_holder_carries_all_three_components() -> None:
    """``SpineCore`` is a frozen dataclass with three named components."""
    from lca.plugins.observability.spine.core import SpineCore

    producer = _CountingProducer()
    file_sink = _CaptureSink()
    spine = EventSpine(sinks=[file_sink])

    holder = SpineCore(
        event_spine=spine,
        file_sink=file_sink,
        emit_pipeline=producer,
    )

    assert holder.event_spine is spine
    assert holder.file_sink is file_sink
    assert holder.emit_pipeline is producer
    # Frozen: attribute assignment raises.
    with pytest.raises((AttributeError, Exception)):
        holder.event_spine = spine  # type: ignore[misc]


def test_setup_activates_process_local_spine_accessor() -> None:
    """After setup, wrap_instrument / reflectors resolve the live EventSpine.

    ADR-0165.1 production gap: spine.core used to publish ``event_spine``
    without calling ``set_active_spine_accessor``, so every wrap and
    reflector silently no-op'd. This pins the activation contract.
    """
    from lca.harness.declarative.compile.instrument_wrap import (
        resolve_active_spine,
        set_active_spine_accessor,
    )
    from lca.plugins.observability.spine.core import setup
    from lca.plugins.observability.spine.reflectors import runtime as runtime_reflector

    previous = set_active_spine_accessor(None)
    runtime_reflector.set_active_spine(None)
    try:
        file_sink = _CaptureSink()
        ctx = _StubPluginContext(
            emit_pipeline=_CountingProducer(),
            file_sink=file_sink,
        )
        import asyncio

        asyncio.run(setup.setup(ctx, config={}))
        spine_core = ctx.provided["event_spine"]

        assert resolve_active_spine() is spine_core.event_spine
        assert runtime_reflector.get_active_spine() is spine_core.event_spine
    finally:
        set_active_spine_accessor(previous)
        runtime_reflector.set_active_spine(None)
