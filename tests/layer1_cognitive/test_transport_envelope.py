from __future__ import annotations

from lca.contracts.models.observability.plan_ref import plan_ref_scope
from lca.layer1_cognitive.transport_envelope import mint_transport_envelope


def test_transport_envelope_marks_unbound_compatibility_path() -> None:
    envelope = mint_transport_envelope(
        operation="delegate",
        decision_ref="dec_transport",
        protocol="a2a",
        target="researcher",
    )

    assert envelope.plan_ref == "legacy-transport"
    assert envelope.metadata["plan_ref_source"] == "compatibility"
    assert envelope.policy_verdict_refs == ()


def test_transport_envelope_preserves_plan_ref_without_fabricating_gate_allows() -> None:
    with plan_ref_scope("compiled_transport_plan"):
        envelope = mint_transport_envelope(
            operation="delegate",
            decision_ref="dec_transport",
            protocol="a2a",
            target="researcher",
        )

    assert envelope.plan_ref == "compiled_transport_plan"
    assert envelope.metadata["plan_ref_source"] == "compiled"
    assert envelope.policy_verdict_refs == ()
