"""ManifestSink — the typed emit path for ContextManifested (PR2 / PR3a).

The Hub is the sole caller of ``ContextManifested.emit``; the sink
abstraction is the seam between the Hub and the underlying store
(``RunStore`` in tests, ``journal.facade.record`` in production).

The seam is a Protocol so alternative sinks (e.g. a tracing-only sink
for read-only runs) can be plugged in without modifying the Hub.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.observability.journal import ContextManifested


@runtime_checkable
class ManifestSink(Protocol):
    """A typed sink for the ``ContextManifested`` event.

    Implementations MUST be idempotent (a fold may run twice during
    replay) and MUST accept the manifest payload as the only required
    argument.  The ``extra`` keyword is for forward compatibility
    (e.g. ``persist_full_prompt``, ``step``).
    """

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested: ...


class NullSink:
    """No-op sink (default for offline tests that don't care about the journal)."""

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        return event


class RunStoreSink:
    """RunStore-backed sink (test path)."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        return self._store.append(event)


class JournalSink:
    """Production sink — emit via the global journal record path.

    The Hub's default sink is always ``JournalSink``.  The sink holds
    no state; the gate is the dual-write flag in cognitive_loop_settings.
    """

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        from lca.layer0_infra.cognitive_loop_settings import get_cognitive_loop_settings
        from lca.layer0_infra.observability import record as _journal_record

        if not get_cognitive_loop_settings().context_manifest_dual_write:
            return event
        return _journal_record(event)


def default_sink() -> ManifestSink:
    """Return the production sink — used when the Hub is built without
    an explicit sink (the common case)."""
    return JournalSink()
