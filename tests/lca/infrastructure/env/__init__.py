"""Tests for lca.infrastructure.env — pure constants (K7 bootstrap).

Verifies the shape and minimum coverage of the three whitelist constants.
These constants are the SSOT for which keys ``.env`` may set; missing entries
mean legitimate LCA configuration cannot be loaded. The floor counts
(BOOTSTRAP_NAMES ≥ 30, BOOTSTRAP_PREFIXES ≥ 10, BOOTSTRAP_FORBIDDEN ≥ 3) are
the PR-1 acceptance gate.
"""

from __future__ import annotations

from lca.infrastructure.env.bootstrap import (
    BOOTSTRAP_FORBIDDEN,
    BOOTSTRAP_NAMES,
    BOOTSTRAP_PREFIXES,
)


def test_bootstrap_names_is_frozenset_with_minimum_coverage() -> None:
    """The exact-name whitelist covers Python / shell / VCS / network trust."""
    assert isinstance(BOOTSTRAP_NAMES, frozenset)
    assert len(BOOTSTRAP_NAMES) >= 30, (
        f"BOOTSTRAP_NAMES floor is 30 entries, got {len(BOOTSTRAP_NAMES)}"
    )
    # Spot-check: a Python + venv key, a VCS key, a network-trust key.
    for required in ("PATH", "PYTHONPATH", "GIT_SSH", "HTTP_PROXY", "SSL_CERT_FILE"):
        assert required in BOOTSTRAP_NAMES, f"missing bootstrap name {required!r}"


def test_bootstrap_prefixes_is_tuple_with_minimum_coverage() -> None:
    """The prefix whitelist covers LCA + deepseek + Freedesktop + LCA deployment."""
    assert isinstance(BOOTSTRAP_PREFIXES, tuple)
    assert len(BOOTSTRAP_PREFIXES) >= 10, (
        f"BOOTSTRAP_PREFIXES floor is 10 entries, got {len(BOOTSTRAP_PREFIXES)}"
    )
    # Spot-check the four required buckets.
    for required_prefix in ("LCA_", "DSH_", "XDG_", "LLM_", "GATEWAY_", "LOBE_"):
        assert required_prefix in BOOTSTRAP_PREFIXES, (
            f"missing bootstrap prefix {required_prefix!r}"
        )


def test_bootstrap_forbidden_includes_lca_profile_and_secrets() -> None:
    """The hard blacklist covers argv-controlled + secret material entries."""
    assert isinstance(BOOTSTRAP_FORBIDDEN, frozenset)
    assert len(BOOTSTRAP_FORBIDDEN) >= 3, (
        f"BOOTSTRAP_FORBIDDEN floor is 3 entries, got {len(BOOTSTRAP_FORBIDDEN)}"
    )
    # ADR-0115 D5: LCA_PROFILE must come from argv, not .env.
    assert "LCA_PROFILE" in BOOTSTRAP_FORBIDDEN
    # LCA_INTERNAL_INJECTION protects the kernel internal flag namespace.
    assert "LCA_INTERNAL_INJECTION" in BOOTSTRAP_FORBIDDEN
    # LCA_KERNEL_KEY routes through the LLM resolver, not .env.
    assert "LCA_KERNEL_KEY" in BOOTSTRAP_FORBIDDEN


def test_lca_inventory_prefixes_present() -> None:
    """PR-1 inventory prefixes (from grep os.environ / os.getenv) are covered.

    The actual deployment prefixes discovered during PR-1 C1.1 stocktake —
    if a new LCA env key is added, this test fails until the prefix list is
    updated alongside the change.
    """
    for prefix in (
        "LLM_",
        "GATEWAY_",
        "LOBE_",
        "LOBEHUB_",
        "ONLYBOXES_",
        "MARKET_",
        "AGENCY_",
        "WAL_",
        "DB_",
        "S3_",
        "REDIS_",
        "OTEL_",
        "VAULT_",
    ):
        assert prefix in BOOTSTRAP_PREFIXES, (
            f"LCA inventory prefix {prefix!r} missing from BOOTSTRAP_PREFIXES"
        )


def test_bootstrap_constants_block_lca_profile_via_forbidden_short_circuit() -> None:
    """LCA_PROFILE's argv-only guarantee is the forbidden-list short-circuit.

    The ``LCA_`` prefix legitimately matches ``LCA_PROFILE``; protection
    comes from :data:`BOOTSTRAP_FORBIDDEN` being checked before the prefix
    branch in :func:`filter_env_keys`. This test asserts only that
    ``LCA_PROFILE`` is not also in :data:`BOOTSTRAP_NAMES` — adding it there
    would let a future refactor that forgets the forbidden short-circuit
    silently re-allow ``.env`` to override the profile selection.
    """
    assert "LCA_PROFILE" not in BOOTSTRAP_NAMES
    assert "LCA_PROFILE" in BOOTSTRAP_FORBIDDEN
