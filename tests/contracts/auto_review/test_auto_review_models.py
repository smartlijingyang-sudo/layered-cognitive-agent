import pytest
from pydantic import ValidationError

from lca.contracts.models.auto_review.models import (
    AutoReviewAction,
    AutoReviewMode,
    AutoReviewVerdict,
    compute_action_fingerprint,
)


def test_auto_review_enums():
    assert AutoReviewMode.OFF == "off"
    assert AutoReviewMode.SHADOW == "shadow"
    assert AutoReviewMode.ENFORCE == "enforce"

    assert AutoReviewAction.ALLOW == "allow"
    assert AutoReviewAction.ADAPT == "adapt"
    assert AutoReviewAction.ESCALATE == "escalate"
    assert AutoReviewAction.BLOCK == "block"


def test_auto_review_verdict_frozen():
    verdict = AutoReviewVerdict(
        action=AutoReviewAction.ALLOW,
        reason="Safe operation",
    )
    with pytest.raises(ValidationError):
        verdict.action = AutoReviewAction.BLOCK  # type: ignore


def test_action_fingerprint_deterministic():
    fp1 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/data"})
    fp2 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/data"})
    fp3 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/other"})
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 64
