"""K3 + ADR-0116: verify boot diagnostics reach structlog during ``_boot_context``.

Strategy
--------
Directly invoke :func:`lca_kernel.boot._emit_boot_events` with a captured
structlog scope and a captured journal backend.

We avoid going through the full cordis fiber boot path because
``PluginDefinition`` requires the ``@plugin`` decorator + plugin contract
which is overkill for testing the kernel's emit behavior. We do NOT attempt
to spawn real fibers in this file; fiber-spawning behavior is exercised by
the integration tests in ``tests/test_plugin_tree_single_owner.py`` and
``tests/lca_kernel/test_lifecycle.py``.

What is asserted
----------------
- :func:`lca_kernel.boot._emit_boot_events` logs ``boot.profile_resolved``,
  then ``boot.observability_assembled``, then one ``boot.pending_event`` per
  buffered :class:`BootPluginFiberSpawned`.
- K3 runs before Session bind, so ``Session.append`` is unreachable and boot
  diagnostics have no journal path: a bound journal backend receives nothing.
- A missing or raising ``observability`` seam never propagates out of boot.
- ``JOURNAL_EVENT_CLASSES`` catalog exposes all three boot event types
  (regression guard against accidental removal).
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from cordis import Context

from lca.contracts.models.observability.journal.catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.models.observability.journal.journal import BootPluginFiberSpawned
from lca.contracts.observability.journal.store import JournalStoreBackend
from lca.infrastructure.observability import AttributePolicy
from lca.infrastructure.observability.journal.backends.memory import InMemoryJournalStore
from lca.infrastructure.observability.journal.engine.engine import RunStore
from lca_kernel.boot.boot import _emit_boot_events  # pyright: ignore[reportPrivateUsage]
from lca_kernel.boot.stages import Stage
from lca_kernel.runtime.observability import make_minimal_bound


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


def test_emit_boot_events_logs_without_a_journal_seam() -> None:
    """A None journal seam narrows ``bound_seams``; boot diagnostics still log."""
    ctx = Context()
    ctx.provide("observability", make_minimal_bound(journal=None))
    with structlog.testing.capture_logs() as logs:
        _emit_boot_events(
            ctx,
            pending_events=[],
            products=_FakeProducts(),
            topo_order=(),
            boot_started=time.monotonic(),
        )

    events = {entry["event"] for entry in logs}
    assert "boot.profile_resolved" in events
    assembled = next(entry for entry in logs if entry["event"] == "boot.observability_assembled")
    assert "journal" not in assembled["bound_seams"]


def test_emit_boot_events_logs_three_event_kinds_in_order() -> None:
    """End-to-end: _emit_boot_events logs profile + observability + buffered fiber events."""
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
    with structlog.testing.capture_logs() as logs:
        _emit_boot_events(
            ctx,
            pending_events=pending,
            products=_FakeProducts(),
            topo_order=("p-alpha", "p-beta"),
            boot_started=time.monotonic(),
        )

    # ADR-0284's fail-soft ``boot.platform_file_missing`` warning lands between
    # the observability line and the pending loop whenever the host LCA home is
    # missing a tier-1 file, so it is filtered out of the order assertion.
    names = [entry["event"] for entry in logs if entry["event"] != "boot.platform_file_missing"]
    assert names == [
        "boot.profile_resolved",
        "boot.observability_assembled",
        "boot.pending_event",
        "boot.pending_event",
    ]

    profile_entry = next(entry for entry in logs if entry["event"] == "boot.profile_resolved")
    assert profile_entry["plugin_count"] == 2
    assert profile_entry["profile_path"] == "<test>"

    obs_entry = next(entry for entry in logs if entry["event"] == "boot.observability_assembled")
    assert "journal" in obs_entry["bound_seams"]

    # K3 runs before Session bind, so boot diagnostics have no journal path:
    # a bound backend must stay empty (single-track Session.append, no bypass).
    assert capture.captured == []


def test_emit_boot_events_tolerates_a_raising_observability_seam() -> None:
    """A seam lookup raising KeyError/TypeError must not crash boot (``_safe_inject``)."""

    class _RaisingCtx:
        def inject(self, _key: str, default: Any = None) -> Any:
            raise TypeError("synthetic seam failure")

    with structlog.testing.capture_logs() as logs:
        _emit_boot_events(
            _RaisingCtx(),  # type: ignore[arg-type]
            pending_events=[],
            products=_FakeProducts(),
            topo_order=(),
            boot_started=time.monotonic(),
        )

    assembled = next(entry for entry in logs if entry["event"] == "boot.observability_assembled")
    assert assembled["bound_seams"] == ()


def test_emit_boot_events_handles_empty_topo_order() -> None:
    """Empty plugin list → ``boot.profile_resolved`` with plugin_count=0."""
    capture = _CaptureStore()
    ctx = _ctx_with_journal(capture)
    with structlog.testing.capture_logs() as logs:
        _emit_boot_events(
            ctx,
            pending_events=[],
            products=_FakeProducts(),
            topo_order=(),
            boot_started=time.monotonic(),
        )

    names = [entry["event"] for entry in logs if entry["event"] != "boot.platform_file_missing"]
    assert names == ["boot.profile_resolved", "boot.observability_assembled"]
    profile_entry = next(entry for entry in logs if entry["event"] == "boot.profile_resolved")
    assert profile_entry["plugin_count"] == 0
    assert capture.captured == []


def test_emit_boot_events_structlog_records_plugin_id() -> None:
    """Regression: structlog ``boot.pending_event`` must carry plugin_id/layer/kind/status.

    Bug fix (poteto-mode investigation 2026-09-14): prior to the fix, the
    line in :func:`_emit_boot_events` only bound ``event_type`` and dropped
    every field of the buffered :class:`BootPluginFiberSpawned`. Operators
    staring at the kernel stderr could not tell which plugin_id produced
    which line, and the only way to enumerate the boot was to re-run
    ``resolve_profile`` in Python. This test asserts that all six
    identifying fields reach the log record.
    """
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
    ]
    with structlog.testing.capture_logs() as logs:
        _emit_boot_events(
            ctx,
            pending_events=pending,
            products=_FakeProducts(),
            topo_order=("p-alpha",),
            boot_started=time.monotonic(),
        )

    boot_pending = [entry for entry in logs if entry.get("event") == "boot.pending_event"]
    assert len(boot_pending) == 1, f"expected one boot.pending_event, got {logs!r}"
    entry = boot_pending[0]
    assert entry["plugin_id"] == "p-alpha", entry
    assert entry["layer"] == "L2", entry
    assert entry["kind"] == "provider", entry
    assert entry["status"] == "ok", entry
    assert entry["duration_ms"] == 12.3, entry
    assert entry["event_type"] == "BootPluginFiberSpawned", entry
