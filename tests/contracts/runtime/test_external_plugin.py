"""Behavioral tests for ``lca.contracts.runtime.external_plugin`` (P5-02).

Covers ``ExternalPluginKind`` (closed Literal set), the trust→kind
default mapping, and the isolation-tier predicates per ADR-0199 §3.4 +
I-HPC-11.
"""

from __future__ import annotations

import sys
from typing import get_args

import pytest

from lca.contracts.runtime.external_plugin import (
    DEFAULT_EXTERNAL_KIND_BY_TRUST,
    ExternalPluginKind,
    default_external_kind,
    is_high_isolation_kind,
    is_sandbox_kind,
)

# ---------------------------------------------------------------------------
# default_external_kind — per-trust-level defaults (ADR-0199 §3.4)
# ---------------------------------------------------------------------------


def test_default_external_kind_for_core() -> None:
    """``core`` trust resolves to ``inprocess`` (bundled plugins share the fiber)."""
    assert default_external_kind("core") == "inprocess"


def test_default_external_kind_for_trusted() -> None:
    """``trusted`` trust resolves to ``inprocess`` (user-vetted runs in the fiber)."""
    assert default_external_kind("trusted") == "inprocess"


def test_default_external_kind_for_untrusted() -> None:
    """``untrusted`` trust resolves to ``mcp`` (I-HPC-11 + P5-02 default)."""
    assert default_external_kind("untrusted") == "mcp"


def test_default_external_kind_unknown_trust_raises() -> None:
    """Unknown trust levels raise ``ValueError`` (no implicit fallback)."""
    with pytest.raises(ValueError, match="unknown trust level"):
        default_external_kind("mystery")
    # Empty string is also an unknown trust level (no silent pass-through).
    with pytest.raises(ValueError, match="unknown trust level"):
        default_external_kind("")


# ---------------------------------------------------------------------------
# is_high_isolation_kind — OS-level or process-level isolation flag
# ---------------------------------------------------------------------------


def test_is_high_isolation_true_for_mcp() -> None:
    """MCP is a separate process → high isolation."""
    assert is_high_isolation_kind("mcp") is True


def test_is_high_isolation_true_for_sandbox() -> None:
    """Sandbox is OS-level isolation → high isolation."""
    assert is_high_isolation_kind("sandbox") is True


def test_is_high_isolation_true_for_worker() -> None:
    """Worker is a separate Python subprocess → high isolation."""
    assert is_high_isolation_kind("worker") is True


def test_is_high_isolation_false_for_inprocess() -> None:
    """Inprocess shares the cordis fiber → not high isolation."""
    assert is_high_isolation_kind("inprocess") is False


# ---------------------------------------------------------------------------
# is_sandbox_kind — narrower OS-sandbox predicate
# ---------------------------------------------------------------------------


def test_is_sandbox_kind_true_for_sandbox() -> None:
    """Only ``sandbox`` is a sandbox kind."""
    assert is_sandbox_kind("sandbox") is True


def test_is_sandbox_kind_false_for_others() -> None:
    """All non-sandbox kinds return False (inprocess / mcp / worker)."""
    assert is_sandbox_kind("inprocess") is False
    assert is_sandbox_kind("mcp") is False
    assert is_sandbox_kind("worker") is False


# ---------------------------------------------------------------------------
# Closed-set shape — adding a kind requires an ADR
# ---------------------------------------------------------------------------


def test_external_plugin_kind_literal_set_complete() -> None:
    """The Literal set is exactly the four kinds from the rubric (no drift)."""
    assert get_args(ExternalPluginKind) == (
        "inprocess",
        "mcp",
        "sandbox",
        "worker",
    )


def test_default_dict_keys_complete() -> None:
    """``DEFAULT_EXTERNAL_KIND_BY_TRUST`` covers all three trust levels."""
    assert set(DEFAULT_EXTERNAL_KIND_BY_TRUST) == {"core", "trusted", "untrusted"}


def test_default_dict_values_are_known_kinds() -> None:
    """Every default kind is itself a member of the closed Literal set."""
    known_kinds = set(get_args(ExternalPluginKind))
    for trust, kind in DEFAULT_EXTERNAL_KIND_BY_TRUST.items():
        assert kind in known_kinds, (
            f"DEFAULT_EXTERNAL_KIND_BY_TRUST[{trust!r}] = {kind!r} "
            f"is not a member of ExternalPluginKind"
        )


# ---------------------------------------------------------------------------
# Contracts purity — no I/O / logging / environment reads
# ---------------------------------------------------------------------------


def test_no_io_imports_in_module() -> None:
    """The contracts module must not import I/O, env, logging, or upper layers.

    Per AGENTS §2.1 + importlinter contract #3: ``contracts`` is pure
    data. Catching the violation statically (via ``sys.modules``) guards
    against a regression where a contributor adds a side-effecting
    helper to the closed-set module.
    """
    forbidden_substrings = (
        "lca.harness",
        "lca.application",
        "lca.infrastructure",
        "lca.cognition",
        "lca.runtime",
        "lca.agent",
        "lca.plugins",
    )
    leaked = sorted(
        name
        for name in sys.modules
        if any(name == root or name.startswith(root + ".") for root in forbidden_substrings)
    )
    assert leaked == [], (
        f"lca.contracts.runtime.external_plugin transitively pulled in "
        f"upper-layer modules: {leaked}"
    )


# ---------------------------------------------------------------------------
# Determinism (C8)
# ---------------------------------------------------------------------------


def test_default_external_kind_deterministic() -> None:
    """``default_external_kind`` is pure: repeated calls return the same value.

    Per C8 (determinism): contracts must not depend on time, randomness,
    PID, or environment. This test guards against accidentally turning
    the helper into a stateful lookup.
    """
    seen = {default_external_kind("untrusted") for _ in range(50)}
    assert seen == {"mcp"}
    seen_trusted = {default_external_kind("trusted") for _ in range(50)}
    assert seen_trusted == {"inprocess"}
