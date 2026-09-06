from __future__ import annotations

import pytest

from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt


def test_effect_receipt_carries_idempotent_success() -> None:
    receipt = EffectReceipt(
        invocation_id="invoke-1",
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="plan:step:1",
        provider="crm.update",
        output_ref="artifact:result",
    )

    assert receipt.outcome is EffectOutcome.SUCCEEDED
    assert receipt.output_ref == "artifact:result"


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "invocation_id": "i",
            "outcome": EffectOutcome.SUCCEEDED,
            "idempotency_key": "",
            "provider": "p",
        },
        {
            "invocation_id": "i",
            "outcome": EffectOutcome.SUCCEEDED,
            "idempotency_key": "k",
            "provider": "p",
            "error_code": "E",
        },
        {
            "invocation_id": "i",
            "outcome": EffectOutcome.FAILED,
            "idempotency_key": "k",
            "provider": "p",
        },
        {
            "invocation_id": "i",
            "outcome": EffectOutcome.SUCCEEDED,
            "idempotency_key": "k",
            "provider": "p",
            "retryable": True,
        },
    ],
)
def test_effect_receipt_rejects_inconsistent_state(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EffectReceipt(**kwargs)


def test_gateway_receipt_is_normalized() -> None:
    from lca.contracts.harness.act.effect_receipt import receipt_from_dispatcher

    receipt = receipt_from_dispatcher(
        {"idempotency_key": "k-1", "output_ref": "artifact://x"},
        invocation_id="invoke-1",
        provider="crm.update",
    )

    assert receipt.idempotency_key == "k-1"
    assert receipt.output_ref == "artifact://x"
