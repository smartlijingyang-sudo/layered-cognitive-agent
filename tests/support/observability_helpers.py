"""Test helpers for constructing BoundObservability instances.

The facade rewrite removed the monolithic ``ObservabilityHub`` in favour of a
4-field ``BoundObservability`` (journal / tracer / policy / scorers). Tests
that previously built a hub now need to assemble the four backends they
actually exercise. This helper exposes one canonical factory plus small
composables for common patterns (memory-only, with a tracer, with a filter
projector).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.models.observability.journal import (
    JournalEvent,
    RuntimeObserved,
    StampedEvent,
)
from lca.contracts.observability.ports import AttributePolicyBackend
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability import (
    RunStore,
)
from lca.layer0_infra.observability.facade import BoundObservability
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity


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

    ``otel_tracer`` (raw OTel ``Tracer`` instance) wires an ``OtelProjector`` into
    the journal projections so journal events produce OTel spans (matching the
    old ``ObservabilityHub`` behavior where ``llm.chat`` etc. were emitted).
    """
    from lca.layer0_infra.observability.journal.otel_projector import OtelProjector

    policy_obj = AttributePolicy(verbosity=verbosity, redact=redact)
    policy: AttributePolicyBackend = policy_obj
    all_projections: list[JournalProjector] = list(projections)
    if otel_tracer is not None:
        all_projections.insert(0, OtelProjector(otel_tracer))
    store = RunStore(policy=policy_obj, projections=all_projections)
    # Wrap the store in a thin backend adapter so it satisfies JournalBackend
    # (``BoundObservability.journal`` requires ``write``, not ``append``).
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
        from lca.contracts.models.observability.diagnostic import DiagnosticCategory

        self._category = DiagnosticCategory(target_category)
        self._sink = sink

    def on_event(self, stamped: StampedEvent) -> None:
        if not isinstance(stamped.event, RuntimeObserved):
            return
        from lca.contracts.models.observability.diagnostic import DiagnosticCategory
        from lca.contracts.models.observability.event import RuntimeKind

        # Inline mapping (was in run_diagnostics._CATEGORY_BY_KIND before its deletion).
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
