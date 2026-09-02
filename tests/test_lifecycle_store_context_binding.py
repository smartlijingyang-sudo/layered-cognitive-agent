"""Production gap: session.lifecycle_store must be ContextVar-bound during execute.

Without ``set_lifecycle_store``, step_emitter silently no-ops and journal.json
flushes as steps=[] / outcome=stopped even when the run completed.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.plugins.seams.observability.run_ledger import _StepTreeBundle
from lca.runtime import step_lifecycle
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_lifecycle_store


def test_contextvar_bound_store_receives_steps_and_flushes_completed(
    tmp_path: Path,
) -> None:
    """Bind session store → open/close step → flush(outcome=completed)."""
    run_dir = tmp_path / "runs" / "run_bind"
    run_dir.mkdir(parents=True)
    store = build_step_lifecycle_store(
        run_id="run_bind",
        trace_id="trace_bind",
        metadata=BuildJournalMetadata(
            agent_role="solo",
            strategy_key="solo",
            objective="bind regression",
        ),
    )
    token = step_lifecycle.set_lifecycle_store(store)
    try:
        step_lifecycle.open_step(phase="think")
        step_lifecycle.close_step(outcome="ok")
    finally:
        step_lifecycle.reset_lifecycle_store(token)

    backend = StepGroupedBackend(
        output_path=run_dir / "journal.json",
        lifecycle_store=store,
    )

    class _Narr:
        def write(self, document: object) -> None:
            del document

    bundle = _StepTreeBundle(backend=backend, narrative_writer=_Narr())
    bundle.flush(outcome="completed")

    doc = json.loads((run_dir / "journal.json").read_text())
    assert doc["schema"] == "lca.journal/3"
    assert len(doc["steps"]) == 1
    assert doc["steps"][0]["phase"] == "think"
    assert doc["metadata"]["outcome"] == "completed"
    assert doc["metadata"]["total_steps"] == 1


def test_flush_default_without_context_steps_stays_empty_but_outcome_honored(
    tmp_path: Path,
) -> None:
    """Even with zero steps, flush must record the real terminal outcome."""
    run_dir = tmp_path / "runs" / "run_empty"
    run_dir.mkdir(parents=True)
    store = build_step_lifecycle_store(
        run_id="run_empty",
        trace_id="trace_empty",
        metadata=BuildJournalMetadata(
            agent_role="solo",
            strategy_key="solo",
            objective="empty",
        ),
    )
    backend = StepGroupedBackend(
        output_path=run_dir / "journal.json",
        lifecycle_store=store,
    )

    class _Narr:
        def write(self, document: object) -> None:
            del document

    _StepTreeBundle(backend=backend, narrative_writer=_Narr()).flush(outcome="completed")
    doc = json.loads((run_dir / "journal.json").read_text())
    assert doc["steps"] == []
    assert doc["metadata"]["outcome"] == "completed"
