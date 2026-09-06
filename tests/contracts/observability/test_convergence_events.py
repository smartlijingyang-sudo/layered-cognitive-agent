"""Convergence session event catalog tests (ADR-0196)."""

from __future__ import annotations

from lca.contracts.harness.memory.events import (
    ConvergenceEvaluatedCommitted,
    DeliveryEvidenceCommitted,
    PromptSurfaceRenderedCommitted,
)
from lca.contracts.observability.event.meta_event_taxonomy import all_session_meta_event_types


def test_convergence_events_in_meta_taxonomy() -> None:
    types = all_session_meta_event_types()
    assert DeliveryEvidenceCommitted._event_type in types
    assert ConvergenceEvaluatedCommitted._event_type in types
    assert PromptSurfaceRenderedCommitted._event_type in types
