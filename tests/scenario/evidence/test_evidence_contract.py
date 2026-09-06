from __future__ import annotations

import pytest

from lca.contracts.harness.perceive.evidence import Evidence


def test_evidence_is_auditable() -> None:
    evidence = Evidence("e1", "doc://42", "quoted fact", 0.92, title="Source")

    assert evidence.source_ref == "doc://42"
    assert evidence.relevance == 0.92


@pytest.mark.parametrize("relevance", [-0.1, 1.1])
def test_evidence_rejects_invalid_relevance(relevance: float) -> None:
    with pytest.raises(ValueError):
        Evidence("e1", "doc://42", "quoted fact", relevance)
