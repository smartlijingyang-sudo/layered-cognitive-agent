"""Tests for explicit normalization of declarative effect gateway outputs."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError
from lca.harness.declarative.effect_receipt import adapt_effect_receipt


def test_plain_mapping_remains_the_domain_output() -> None:
    """A handler result is not mistaken for a receipt merely because it has result data."""
    output = {"result": "domain value", "metadata": "handler-owned"}

    view = adapt_effect_receipt(output)

    assert view.output is output
    assert view.audit_record is output
    assert view.is_idempotency_receipt is False


def test_complete_idempotency_receipt_exposes_domain_result() -> None:
    """A verified replay receipt preserves audit metadata but publishes its result."""
    observation = Observation(observation_id="obs-1", success=True, payload="complete")
    receipt = {
        "receipt": "body.act.completed",
        "result": observation,
        "plan_ref": "plan-1",
        "idempotency_key": "effect-1",
        "operation": "body.act",
    }

    view = adapt_effect_receipt(receipt)

    assert view.output is observation
    assert view.audit_record == receipt
    assert view.audit_record is not receipt
    assert view.is_idempotency_receipt is True


def test_incomplete_receipt_fails_closed() -> None:
    """A receipt-shaped mapping cannot hide missing replay-critical fields."""
    with pytest.raises(DeclarativeValidationError, match="missing required fields") as exc_info:
        adapt_effect_receipt({"receipt": "body.act.completed", "result": "complete"})

    assert exc_info.value.code == "RT-003"
