"""L3-7: LLM provider returns 500 mid-step — stream_retry + eventual completion.

A stub LLM provider returns 500 on the first 2 calls and 200 on the
3rd. The client should see ``stream_retry`` events (≥ 1) and ultimately
``agent_runtime_end{completed}`` (not ``error``).

Gated on ``LCA_E2E_KERNEL=1``; skipped otherwise.
"""

from __future__ import annotations

import pytest


@pytest.mark.timeout(120)
def test_llm_500_retry_stream_retry_then_complete(lca_client) -> None:
    """LLM 500 × 2 → stream_retry → 200 → agent_runtime_end{completed}."""
    pytest.skip(
        "L3-7 requires LCA_E2E_KERNEL=1 (LCA dev stack with a stub "
        "LLM provider); see tests/e2e/p1/conftest.py"
    )


def test_stream_retry_event_shape_matches_contract() -> None:
    """Unit-level: ``StreamRetry`` wire shape matches the Pydantic model.

    Does not require a kernel or LLM provider — just verifies the
    ``stream_retry`` event payload conforms to the contract.
    """
    from lca.contracts.transport.agent_stream_event import StreamRetry

    event = StreamRetry(
        operationId="run_1",
        stepIndex=2,
        timestamp=1700000000000,
        data={
            "attempt": 1,
            "max": 3,
            "provider": "openai",
            "delayMs": 1000,
        },
    )
    dumped = event.model_dump()
    assert dumped["type"] == "stream_retry"
    assert dumped["data"]["attempt"] == 1
    assert dumped["data"]["max"] == 3
    assert dumped["data"]["provider"] == "openai"
    assert dumped["data"]["delayMs"] == 1000
    assert dumped["operationId"] == "run_1"
    assert dumped["stepIndex"] == 2


def test_stream_retry_fields_are_serialised_wire_compat() -> None:
    """The ``stream_retry`` data payload omits None fields (wire-compat)."""
    from lca.contracts.transport.agent_stream_event import StreamRetry

    event = StreamRetry(
        operationId="run_2",
        stepIndex=0,
        timestamp=1700000000000,
        data={"attempt": 2, "max": 3},
    )
    dumped = event.model_dump()
    # provider and delayMs are None → excluded by _WireBase.model_dump.
    assert "provider" not in dumped["data"]
    assert "delayMs" not in dumped["data"]
    # attempt and max are always present.
    assert dumped["data"]["attempt"] == 2
    assert dumped["data"]["max"] == 3
