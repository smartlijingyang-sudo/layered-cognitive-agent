from __future__ import annotations

import pytest

from lca.contracts.harness.cancellation import CancellationRequest, CancellationState


def test_cancellation_request_can_be_applied() -> None:
    request = CancellationRequest("task-1", "user requested").apply()

    assert request.state is CancellationState.APPLIED


def test_cancellation_request_requires_identity_and_reason() -> None:
    with pytest.raises(ValueError):
        CancellationRequest("", "user requested")
    with pytest.raises(ValueError):
        CancellationRequest("task-1", "")
