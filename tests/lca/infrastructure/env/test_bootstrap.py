"""Tests for lca.infrastructure.env.bootstrap — constant shape contract.

These tests are the gate from PR-1 §验证: BOOTSTRAP_NAMES ≥ 30,
BOOTSTRAP_PREFIXES ≥ 10, BOOTSTRAP_FORBIDDEN ≥ 3, and every inventory prefix
from the PR-1 stocktake is represented.
"""

from __future__ import annotations

from lca.infrastructure.env.bootstrap import (
    BOOTSTRAP_FORBIDDEN,
    BOOTSTRAP_NAMES,
    BOOTSTRAP_PREFIXES,
)


def test_names_frozenset_and_floor() -> None:
    assert isinstance(BOOTSTRAP_NAMES, frozenset)
    assert len(BOOTSTRAP_NAMES) >= 30


def test_names_contains_core_bootstrap_keys() -> None:
    for key in ("PATH", "PYTHONPATH", "GIT_SSH", "HTTP_PROXY", "SSL_CERT_FILE"):
        assert key in BOOTSTRAP_NAMES


def test_prefixes_tuple_and_floor() -> None:
    assert isinstance(BOOTSTRAP_PREFIXES, tuple)
    assert len(BOOTSTRAP_PREFIXES) >= 10


def test_prefixes_contain_required_buckets() -> None:
    for prefix in ("LCA_", "DSH_", "XDG_", "LLM_", "GATEWAY_", "LOBE_"):
        assert prefix in BOOTSTRAP_PREFIXES


def test_forbidden_frozenset_and_floor() -> None:
    assert isinstance(BOOTSTRAP_FORBIDDEN, frozenset)
    assert len(BOOTSTRAP_FORBIDDEN) >= 3


def test_forbidden_contains_lca_profile_and_internal_flags() -> None:
    assert "LCA_PROFILE" in BOOTSTRAP_FORBIDDEN
    assert "LCA_INTERNAL_INJECTION" in BOOTSTRAP_FORBIDDEN
    assert "LCA_KERNEL_KEY" in BOOTSTRAP_FORBIDDEN


def test_forbidden_does_not_appear_in_allow_lists() -> None:
    """LCA_PROFILE must not be re-allowed by the exact-name allow list.

    The prefix ``LCA_`` legitimately matches ``LCA_PROFILE``; the protection
    is the forbidden-list short-circuit in :func:`filter_env_keys`. This test
    only ensures ``LCA_PROFILE`` is not also in :data:`BOOTSTRAP_NAMES`,
    which would let ``filter_env_keys`` re-allow it before the forbidden
    branch runs.
    """
    assert "LCA_PROFILE" not in BOOTSTRAP_NAMES
