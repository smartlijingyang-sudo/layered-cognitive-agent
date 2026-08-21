"""DefaultEvidencePolicy 决策覆盖(ADR-0065 PR-2 / L5 / L8)。

- classify: hint 优先;缺省时关键字触发升级
- retention: hint 优先;缺省时 RUN_DEFAULT
- should_inline: restricted/confidential 永 False;public/internal ≤64 KiB True
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.evidence import Classification, RetentionClass
from lca.layer0_infra.observability.evidence.policy import DefaultEvidencePolicy


@pytest.fixture
def policy() -> DefaultEvidencePolicy:
    return DefaultEvidencePolicy()


def test_classify_hint_wins(policy: DefaultEvidencePolicy) -> None:
    """hint 显式时覆盖关键字启发式。"""
    payload_with_secret = b"password=hunter2"
    # 即使 payload 含 'password',hint=PUBLIC → 仍 PUBLIC
    assert policy.classify(payload_with_secret, hint=Classification.PUBLIC) == Classification.PUBLIC


def test_classify_keyword_triggers_restricted(policy: DefaultEvidencePolicy) -> None:
    """无 hint 时关键字触发 RESTRICTED。"""
    for keyword in (
        b"password=hunter2",
        b"api_key: ABC",
        b"private_key: ---",
        b"access_token=xyz",
        b"refresh_token=abc",
    ):
        result = policy.classify(keyword)
        assert result == Classification.RESTRICTED, keyword


def test_classify_default_internal_for_text(policy: DefaultEvidencePolicy) -> None:
    """无 hint / 无关键字 → INTERNAL(text 媒体默认)。"""
    assert policy.classify(b"hello world", media_type="text/plain") == Classification.INTERNAL


def test_classify_extra_keywords(policy: DefaultEvidencePolicy) -> None:
    """可扩展关键字集合。"""
    custom = DefaultEvidencePolicy(extra_restricted_keywords=(b"my-tenant-secret",))
    assert custom.classify(b"my-tenant-secret=oops") == Classification.RESTRICTED


def test_should_inline_restricted_never(policy: DefaultEvidencePolicy) -> None:
    """restricted / confidential 永不内联(0065 L8)。"""
    assert policy.should_inline(b"x", classification=Classification.RESTRICTED) is False
    assert policy.should_inline(b"x", classification=Classification.CONFIDENTIAL) is False


def test_should_inline_threshold(policy: DefaultEvidencePolicy) -> None:
    """public / internal ≤64 KiB 内联;>64 KiB 走 ref。"""
    threshold = 64 * 1024
    assert policy.should_inline(b"x" * threshold, classification=Classification.INTERNAL)
    assert not policy.should_inline(b"x" * (threshold + 1), classification=Classification.INTERNAL)


def test_should_inline_custom_threshold() -> None:
    custom = DefaultEvidencePolicy(inline_threshold_bytes=128)
    assert custom.should_inline(b"x" * 100, classification=Classification.INTERNAL)
    assert not custom.should_inline(b"x" * 200, classification=Classification.INTERNAL)


def test_should_inline_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        DefaultEvidencePolicy(inline_threshold_bytes=0)


def test_retention_hint_wins(policy: DefaultEvidencePolicy) -> None:
    assert policy.retention(b"x", hint=RetentionClass.PERMANENT) == RetentionClass.PERMANENT


def test_retention_default_run_default(policy: DefaultEvidencePolicy) -> None:
    assert policy.retention(b"x") == RetentionClass.RUN_DEFAULT
