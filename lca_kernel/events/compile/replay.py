"""Replay observability projections from event streams (ADR-0198)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lca.contracts.observability.compile.plan import CompiledObservabilityPlan
from lca_kernel.events.compile.compiler import ObservabilityCompiler


def replay_projection(
    events: Iterable[Any],
    projection_id: str,
    *,
    plan: CompiledObservabilityPlan | None = None,
    **kwargs: Any,
) -> Any:
    """Fold ``events`` through the projection named in the compiled plan.

    Supported projections (P0):
    - ``journal.step_tree`` → :class:`JournalDocument` via plugin fold
    """
    compiled = plan or ObservabilityCompiler.compile()
    if not compiled.ok:
        codes = ", ".join(d.code for d in compiled.diagnostics if d.severity == "error")
        raise RuntimeError(f"observability compile plan invalid: {codes}")

    known = {p.projection_id for p in compiled.projections}
    if projection_id not in known:
        raise ValueError(f"unknown projection_id {projection_id!r}; known={sorted(known)}")

    if projection_id == "journal.step_tree":
        from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

        return fold_step_tree(events, **kwargs)

    raise NotImplementedError(f"replay for projection {projection_id!r} not wired yet")


__all__ = ["replay_projection"]
