"""RA-032: pin the shared ambient evidence-store resolution seam.

``resolve_evidence_store`` concentrates the "current_bound ->
evidence_binding().store -> no-ref when unbound" ritual that used to be
hand-written in both ``safe_executor._resolve_evidence_pair`` and
``approve_gate._route_refusal_to_evidence``. Fail-soft contract: unbound
(unit tests / offline paths) or a binding without a store -> None.
"""

from lca.cognition.body.executor.safe_executor.executor import _resolve_evidence_pair
from lca.infrastructure.observability import (
    BoundObservability,
    bind_backends,
    resolve_evidence_store,
)


def test_unbound_returns_none() -> None:
    assert resolve_evidence_store() is None


def test_bound_with_store_returns_store() -> None:
    store = object()
    with bind_backends(BoundObservability(evidence_store=store)):
        assert resolve_evidence_store() is store


def test_bound_without_store_returns_none() -> None:
    with bind_backends(BoundObservability()):
        assert resolve_evidence_store() is None


def test_pair_delegates_store_resolution_and_keeps_tuple_shape() -> None:
    store, policy = object(), object()
    with bind_backends(BoundObservability(evidence_store=store, evidence_policy=policy)):
        assert _resolve_evidence_pair() == (store, policy)
    assert _resolve_evidence_pair() == (None, None)
