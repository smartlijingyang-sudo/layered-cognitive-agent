from __future__ import annotations

import pytest

from lca.contracts.harness.gate.timeout_recovery import TimeoutAction, TimeoutRecoveryPolicy


def test_timeout_policy_retries_then_resumes_from_checkpoint() -> None:
    policy = TimeoutRecoveryPolicy(max_retries=1)

    assert policy.decide(0, checkpoint_available=True) is TimeoutAction.RETRY
    assert policy.decide(1, checkpoint_available=True) is TimeoutAction.RESUME
    assert policy.decide(1, checkpoint_available=False) is TimeoutAction.FAIL


def test_timeout_policy_rejects_negative_retry_budget() -> None:
    with pytest.raises(ValueError):
        TimeoutRecoveryPolicy(max_retries=-1)
