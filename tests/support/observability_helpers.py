"""Test helpers for constructing BoundObservability instances.

The facade rewrite removed the monolithic ``ObservabilityHub`` in favour of a
4-field ``BoundObservability`` (journal / tracer / policy / scorers). Tests
that previously built a hub now need to assemble the four backends they
actually exercise. This helper exposes one canonical factory plus a
small ``_RunStoreBackend`` adapter that maps ``RunStore.append`` to the
``JournalBackend.write`` Protocol.

ADR-0192 / ADR-0194 cleanup note: the legacy OTel journal projector
(``lca.infrastructure.observability.journal.otel.projector.OtelProjector``)
is removed; ``otel_tracer`` keyword is kept for backward signature
compatibility but is a no-op now — OTel span emission is the responsibility
of the Session runtime's observers, not the legacy journal fan-out.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.models.observability.journal.journal import (
    JournalEvent,
    RuntimeObserved,
    StampedEvent,
)
from lca.contracts.observability.core.ports import AttributePolicyBackend
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability import (
    RunStore,
)
from lca.infrastructure.observability.adapters.policy import AttributePolicy, Verbosity
from lca.infrastructure.observability.facade import BoundObservability


def make_test_bound(
    *,
    verbosity: Verbosity = Verbosity.STANDARD,
    redact: bool = True,
    projections: Sequence[JournalProjector] = (),
    scorers: tuple[Any, ...] = (),
    tracer: Any | None = None,
    otel_tracer: Any | None = None,
) -> BoundObservability:
    """Construct a ``BoundObservability`` with a memory journal + given policy.

    ``otel_tracer`` (raw OTel ``Tracer`` instance) is accepted for signature
    backward compatibility and is a no-op now — Session observers own
    OTel span emission; legacy journal OTel fan-out was removed.
    """
    del otel_tracer
    policy_obj = AttributePolicy(verbosity=verbosity, redact=redact)
    policy: AttributePolicyBackend = policy_obj
    all_projections: list[JournalProjector] = list(projections)
    store = RunStore(policy=policy_obj, projections=all_projections)
    return BoundObservability(
        journal=_RunStoreBackend(store),
        tracer=tracer,
        policy=policy,
        scorers=scorers,
    )


class _RunStoreBackend:
    """Adapter: ``RunStore.append`` → ``JournalBackend.write``."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    @property
    def store(self) -> RunStore:
        return self._store

    def write(self, event: JournalEvent) -> StampedEvent | None:
        return self._store.append(event)

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.close()


class RuntimeCategoryFilter:
    """JournalProjector that only forwards ``RuntimeObserved`` of a given category."""

    def __init__(self, target_category: Any, sink: JournalProjector) -> None:
        from lca.contracts.models.observability.diagnostic.diagnostic import DiagnosticCategory

        self._category = DiagnosticCategory(target_category)
        self._sink = sink

    def on_event(self, stamped: StampedEvent) -> None:
        if not isinstance(stamped.event, RuntimeObserved):
            return
        from lca.contracts.models.observability.diagnostic.diagnostic import DiagnosticCategory
        from lca.contracts.models.observability.event.event import RuntimeKind

        _kind_to_category: dict[RuntimeKind, DiagnosticCategory] = {
            RuntimeKind.AGENT: DiagnosticCategory.AGENT,
            RuntimeKind.PLUGIN: DiagnosticCategory.PLUGIN,
            RuntimeKind.HOOK: DiagnosticCategory.HOOK,
            RuntimeKind.LLM: DiagnosticCategory.LLM,
            RuntimeKind.TOOL: DiagnosticCategory.TOOL,
            RuntimeKind.MEMORY: DiagnosticCategory.MEMORY,
            RuntimeKind.TRANSPORT: DiagnosticCategory.TRANSPORT,
            RuntimeKind.CODE: DiagnosticCategory.INFRA,
            RuntimeKind.PERMISSION: DiagnosticCategory.INFRA,
            RuntimeKind.COMPACTION: DiagnosticCategory.INFRA,
            RuntimeKind.ERROR: DiagnosticCategory.INFRA,
            RuntimeKind.RETRY: DiagnosticCategory.INFRA,
        }

        observed_category = _kind_to_category.get(RuntimeKind(stamped.event.kind), self._category)
        if observed_category is not self._category:
            return
        self._sink.on_event(stamped)

    def flush(self) -> None:
        self._sink.flush()

    def close(self) -> None:
        self._sink.close()


__all__ = ["RuntimeCategoryFilter", "_RunStoreBackend", "make_test_bound"]
