"""K3 + ADR-0116: verify three boot JournalEvents are emitted during ``_boot_context``.

Strategy
--------
Directly invoke the helpers exposed by ``lca_kernel.boot``:

- :func:`lca_kernel.boot._emit_boot_events` with a captured journal backend
  to verify the three typed events land in journal.

We avoid going through the full cordis fiber boot path because
``PluginDefinition`` requires the ``@plugin`` decorator + plugin contract
which is overkill for testing the kernel's emit behavior. We patch
``_boot_context``'s entry iteration by passing a pre-built pending_events
list and verifying the journal receives BootProfileResolved and
BootObservabilityAssembled. We do NOT attempt to spawn real fibers in this
file; fiber-spawning behavior is exercised by the integration tests in
``tests/test_plugin_tree_single_owner.py`` and ``tests/lca_kernel/test_lifecycle.py``.

What is asserted
----------------
- :func:`lca_kernel.boot._emit_boot_events` writes BootProfileResolved +
  BootObservabilityAssembled + buffered BootPluginFiberSpawned events
  in that order.
- ``BootPluginFiberSpawned.stage`` is the :class:`Stage` IntEnum.
- When journal backend is None, ``_emit_boot_events`` silently no-ops.
- ``JOURNAL_EVENT_CLASSES`` catalog exposes all three boot event types
  (regression guard against accidental removal).
"""

from __future__ import annotations

import time
from typing import Any

from cordis import Context

from lca.contracts.models.observability.journal import (
    BootObservabilityAssembled,
    BootPluginFiberSpawned,
    BootProfileResolved,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.harness.observability.assemble import make_minimal_bound
from lca.infrastructure.observability import AttributePolicy
from lca.infrastructure.observability.journal.backends.memory import InMemoryJournalStore
from lca.infrastructure.observability.journal.engine.engine import RunStore
from lca_kernel.boot import _emit_boot_events  # pyright: ignore[reportPrivateUsage]
from lca_kernel.stages import Stage


class _CaptureStore(JournalStoreBackend):
    """Minimal :class:`JournalStoreBackend` that records stamped events."""

    def __init__(self) -> None:
        self.captured: list[Any] = []
        self._store = InMemoryJournalStore()

    def append(self, stamped: Any) -> Any:
        self.captured.append(stamped)
        return self._store.append(stamped)

    def events(self):  # type: ignore[no-untyped-def]
        return self._store.events()

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __len__(self) -> int:
        return len(self._store)


def _ctx_with_journal(events_capture: _CaptureStore) -> Context:
    """Build a Context whose ``observability`` seam is pre-populated."""
    ctx = Context()
    store = RunStore(
        policy=AttributePolicy(),
        projections=(),
        backend=events_capture,
    )
    bound = make_minimal_bound(journal=store, policy=AttributePolicy())
    ctx.provide("observability", bound)
    return ctx


class _FakeResolved:
    path = "<test>"
    manifest_hash = "deadbeef"
    bundles = ()
    plugins = ()


class _FakeProducts:
    resolved_profile = _FakeResolved()


def test_journal_event_classes_catalog_registers_three_boot_events() -> None:
    """Guard against accidental removal from JOURNAL_EVENT_CLASSES."""
    catalog_names = set(JOURNAL_EVENT_CLASSES.keys())
    assert {
        "BootProfileResolved",
        "BootPluginFiberSpawned",
        "BootObservabilityAssembled",
    } <= catalog_names


def test_emit_boot_events_does_nothing_when_journal_missing() -> None:
    """When BoundObservability.journal is None, _emit_boot_events silently skips."""
    ctx = Context()
    ctx.provide("observability", make_minimal_bound(journal=None))
    # Should not raise.
    _emit_boot_events(
        ctx,
        pending_events=[],
        products=_FakeProducts(),
        topo_order=(),
        boot_started=time.monotonic(),
    )


def test_emit_boot_events_writes_three_event_kinds_in_order() -> None:
    """End-to-end: _emit_boot_events writes BootPluginFiberSpawned + BootProfileResolved + BootObservabilityAssembled."""
    capture = _CaptureStore()
    ctx = _ctx_with_journal(capture)

    pending = [
        BootPluginFiberSpawned(
            plugin_id="p-alpha",
            layer="L2",
            kind="provider",
            stage=Stage.BOOT,
            duration_ms=12.3,
            status="ok",
        ),
        BootPluginFiberSpawned(
            plugin_id="p-beta",
            layer="L3",
            kind="provider",
            stage=Stage.BOOT,
            duration_ms=7.8,
            status="ok",
        ),
    ]
    _emit_boot_events(
        ctx,
        pending_events=pending,
        products=_FakeProducts(),
        topo_order=("p-alpha", "p-beta"),
        boot_started=time.monotonic(),
    )

    kinds = [type(e.event).__name__ for e in capture.captured]
    # BootPluginFiberSpawned first (buffered), then BootProfileResolved, then BootObservabilityAssembled.
    assert kinds == [
        "BootPluginFiberSpawned",
        "BootPluginFiberSpawned",
        "BootProfileResolved",
        "BootObservabilityAssembled",
    ]
    fiber_events = [
        e.event for e in capture.captured if isinstance(e.event, BootPluginFiberSpawned)
    ]
    assert len(fiber_events) == 2
    for ev in fiber_events:
        assert ev.status == "ok"
        assert ev.duration_ms >= 0.0
        # Stage is the Stage IntEnum SSOT. After RunStore policy pass, the
        # Enum may be normalized to its int value (1–6); we accept either.
        assert ev.stage == Stage.BOOT or int(ev.stage) == int(Stage.BOOT)

    profile_event = next(
        e.event for e in capture.captured if isinstance(e.event, BootProfileResolved)
    )
    assert profile_event.plugin_count == 2
    assert profile_event.topo_order == ("p-alpha", "p-beta")

    obs_event = next(
        e.event for e in capture.captured if isinstance(e.event, BootObservabilityAssembled)
    )
    assert obs_event.journal_enabled is True
    assert "journal" in obs_event.bound_seams


def test_emit_boot_events_swallows_journal_write_errors() -> None:
    """When journal.write raises, _emit_boot_events must not crash the kernel."""

    class _RaisingStore:
        def write(self, _event: Any) -> Any:
            raise RuntimeError("synthetic journal failure")

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    ctx = Context()
    ctx.provide("observability", make_minimal_bound(journal=_RaisingStore()))  # type: ignore[arg-type]
    # Should swallow the synthetic failure.
    _emit_boot_events(
        ctx,
        pending_events=[],
        products=_FakeProducts(),
        topo_order=(),
        boot_started=time.monotonic(),
    )


def test_emit_boot_events_handles_empty_topo_order() -> None:
    """Empty plugin list → BootProfileResolved with plugin_count=0."""
    capture = _CaptureStore()
    ctx = _ctx_with_journal(capture)
    _emit_boot_events(
        ctx,
        pending_events=[],
        products=_FakeProducts(),
        topo_order=(),
        boot_started=time.monotonic(),
    )
    kinds = [type(e.event).__name__ for e in capture.captured]
    assert "BootProfileResolved" in kinds
    assert "BootObservabilityAssembled" in kinds
    profile_event = next(
        e.event for e in capture.captured if isinstance(e.event, BootProfileResolved)
    )
    assert profile_event.plugin_count == 0
    assert profile_event.topo_order == ()
