"""Bind observability projections for one Gateway run.

This module owns the observability seam only: it extends the boot-provided
binding with run-local projections and can lazily repair the compatibility
path for sessions created by older callers. Session identity, registration,
and lifecycle transitions remain outside this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from gateway.runs.session.session import RunSession
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_journal import LiveRunProjection, RunJournalFactory
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability import BoundObservability
from lca.infrastructure.observability.facade.settings import ObservabilitySettings


def assemble_run_hub(
    *,
    jsonl_writer: JournalProjector,
    tail: LiveRunProjection,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
) -> BoundObservability:
    """Extend boot observability with immutable projections for one run."""
    del settings
    from lca.harness.observability import make_minimal_bound

    try:
        base: BoundObservability = require_capability(ctx, "observability")
    except MissingCapabilityError:
        from lca.infrastructure.observability.adapters.policy import AttributePolicy
        from lca.infrastructure.observability.facade import BoundObservability as FacadeBound

        minimal = make_minimal_bound()
        return FacadeBound(
            journal=minimal.journal,
            tracer=minimal.tracer,
            policy=AttributePolicy(),
            scorers=minimal.scorers,
        )

    run_bound = base.with_journal_projection(jsonl_writer)
    run_bound = run_bound.with_journal_projection(tail)
    for projection in extra_projectors:
        run_bound = run_bound.with_journal_projection(projection)
    return run_bound


def ensure_session_hub(
    session: RunSession,
    *,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
) -> BoundObservability:
    """Lazily bind observability for a legacy session without creating it."""
    if session.hub is not None:
        return session.hub

    journal_factory = cast("RunJournalFactory", require_capability(ctx, "run_ledger_factory"))
    components = journal_factory.create_run_components(jsonl_path=session.jsonl_path)
    session.tail = components.tail
    hub = assemble_run_hub(
        jsonl_writer=components.writer,
        tail=components.tail,
        ctx=ctx,
        settings=settings,
    )
    session.hub = hub
    return hub


__all__ = ["assemble_run_hub", "ensure_session_hub"]
