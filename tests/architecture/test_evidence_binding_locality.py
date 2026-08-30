from __future__ import annotations

from lca.layer0_infra.observability import BoundObservability, EvidenceBinding


class TestEvidenceBindingLocality:
    def test_evidence_dependencies_are_exposed_as_one_seam(self) -> None:
        store = object()
        policy = object()
        bound = BoundObservability(evidence_store=store, evidence_policy=policy)  # type: ignore[arg-type]

        assert bound.evidence_binding() == EvidenceBinding(store=store, policy=policy)  # type: ignore[arg-type]

    def test_missing_evidence_remains_explicit(self) -> None:
        binding = BoundObservability().evidence_binding()

        assert binding.store is None
        assert binding.policy is None
