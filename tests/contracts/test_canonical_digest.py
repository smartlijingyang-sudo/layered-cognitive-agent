"""ADR-0203 §5.1 — unit tests for ``canonical_digest``.

delete-when: ``canonical_digest`` is replaced or the helper contract
changes (length / prefix / normalization). Locks the canonical-JSON +
sha256-hex SSOT contract so any future refactor must touch this file
first.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from lca.contracts.observability.canonical_digest import canonical_digest


def test_canonical_digest_basic() -> None:
    """Same input → same output; default ``"sha256:"`` prefix + 16 hex chars."""
    payload = {"x": 1, "y": "two"}
    out = canonical_digest(payload)
    assert out.startswith("sha256:")
    assert len(out) == len("sha256:") + 16
    # same input twice → identical output
    assert canonical_digest(payload) == out


def test_canonical_digest_length_parameter() -> None:
    """Different ``length`` returns different prefix-stripped length."""
    payload = {"x": 1, "y": "two"}
    short = canonical_digest(payload, length=12).removeprefix("sha256:")
    medium = canonical_digest(payload, length=16).removeprefix("sha256:")
    long_ = canonical_digest(payload, length=64).removeprefix("sha256:")
    assert len(short) == 12
    assert len(medium) == 16
    assert len(long_) == 64
    # short is a prefix of medium is a prefix of long_
    assert long_.startswith(medium) and medium.startswith(short)


def test_canonical_digest_prefix_parameter() -> None:
    """Custom prefix (``"evt_"`` / empty) is honored."""
    payload = {"x": 1}
    assert canonical_digest(payload, prefix="").startswith("") is True
    assert "sha256:" not in canonical_digest(payload, prefix="")
    assert canonical_digest(payload, prefix="evt_").startswith("evt_")
    # empty-prefix digest equals the bare sha256 of the canonical JSON
    expected_hex = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]
    assert canonical_digest(payload, length=16, prefix="") == expected_hex


def test_canonical_digest_canonicalization() -> None:
    """Dict key order is irrelevant (``sort_keys=True``)."""
    a = canonical_digest({"a": 1, "b": 2, "c": 3})
    b = canonical_digest({"c": 3, "a": 1, "b": 2})
    c = canonical_digest({"b": 2, "c": 3, "a": 1})
    assert a == b == c
    # Nested dict
    nested_a = canonical_digest({"outer": {"a": 1, "b": 2}})
    nested_b = canonical_digest({"outer": {"b": 2, "a": 1}})
    assert nested_a == nested_b


def test_canonical_digest_type_errors() -> None:
    """Negative ``length`` raises ``ValueError``; valid input has no error."""
    with pytest.raises(ValueError, match="length must be"):
        canonical_digest({"x": 1}, length=0)
    with pytest.raises(ValueError, match="length must be"):
        canonical_digest({"x": 1}, length=-1)
    # non-bytes / non-string objects that need ``default=str`` are accepted
    class _Weird:
        def __str__(self) -> str:
            return "weird"

    # Default ``default=str`` lets arbitrary objects serialize via ``str(obj)``.
    assert canonical_digest(_Weird()).startswith("sha256:")
