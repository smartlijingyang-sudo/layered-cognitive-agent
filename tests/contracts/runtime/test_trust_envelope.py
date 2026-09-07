"""Behavioral tests for ``lca.contracts.runtime.trust``.

Covers ``PluginOrigin`` and ``TrustEnvelope`` invariants per ADR-0199
§3.2 / §3.4 and I-HPC-11 (信任默认拒绝).
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.contracts.runtime.trust import (
    EMPTY_TRUST_ENVELOPE,
    PluginOrigin,
    TrustEnvelope,
)


def _origin(
    source: str = "bundled",
    trust: str = "core",
    *,
    enabled_by: str = "profiles/default.yaml",
    discovered_at: str = "bundles/lca.memory.semantic",
) -> PluginOrigin:
    """Build a valid :class:`PluginOrigin` with overridable fields."""
    return PluginOrigin(
        source=source,  # type: ignore[arg-type]
        trust=trust,  # type: ignore[arg-type]
        enabled_by=enabled_by,
        discovered_at=discovered_at,
    )


# ---------------------------------------------------------------------------
# PluginOrigin
# ---------------------------------------------------------------------------


def test_plugin_origin_bundled_requires_core() -> None:
    """bundled must be core (ADR-0199 §3.4)."""
    with pytest.raises(ValueError, match="requires trust='core'"):
        PluginOrigin(
            source="bundled",
            trust="trusted",
            enabled_by="profiles/default.yaml",
            discovered_at="bundles/lca.memory.semantic",
        )


def test_plugin_origin_bundled_untrusted_rejected() -> None:
    """bundled+untrusted is also invalid — bundled plugins ARE core."""
    with pytest.raises(ValueError, match="requires trust='core'"):
        PluginOrigin(
            source="bundled",
            trust="untrusted",
            enabled_by="profiles/default.yaml",
            discovered_at="bundles/lca.memory.semantic",
        )


def test_plugin_origin_project_untrusted_default() -> None:
    """project untrusted is the default and constructs cleanly."""
    origin = _origin(source="project", trust="untrusted")
    assert origin.source == "project"
    assert origin.trust == "untrusted"
    assert origin.enabled_by == "profiles/default.yaml"


def test_plugin_origin_project_trusted_constructs() -> None:
    """project+trusted is allowed when an operator opts in."""
    origin = _origin(source="project", trust="trusted")
    assert origin.trust == "trusted"


def test_plugin_origin_pip_cannot_be_core() -> None:
    """pip+core is rejected (ADR-0199 §3.4)."""
    with pytest.raises(ValueError, match="cannot claim trust='core'"):
        PluginOrigin(
            source="pip",
            trust="core",
            enabled_by="profiles/default.yaml",
            discovered_at="lca_pip_plugin.example",
        )


def test_plugin_origin_user_can_be_trusted() -> None:
    """user+trusted is allowed."""
    origin = _origin(source="user", trust="trusted")
    assert origin.source == "user"
    assert origin.trust == "trusted"


def test_origin_discovered_at_required_nonempty() -> None:
    """Empty discovered_at is rejected."""
    with pytest.raises(ValueError, match="discovered_at"):
        PluginOrigin(
            source="bundled",
            trust="core",
            enabled_by="profiles/default.yaml",
            discovered_at="",
        )


def test_origin_enabled_by_required_nonempty() -> None:
    """Empty enabled_by is rejected."""
    with pytest.raises(ValueError, match="enabled_by"):
        PluginOrigin(
            source="bundled",
            trust="core",
            enabled_by="",
            discovered_at="bundles/lca.memory.semantic",
        )


def test_plugin_origin_is_frozen() -> None:
    """Frozen dataclass rejects attribute assignment."""
    origin = _origin()
    with pytest.raises(dataclasses.FrozenInstanceError):
        origin.source = "pip"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TrustEnvelope
# ---------------------------------------------------------------------------


def _envelope(
    *,
    privileges: frozenset[str] = frozenset({"state.read"}),
    sources: tuple[str, ...] = ("bundled",),
    trusts: tuple[str, ...] = ("core",),
) -> TrustEnvelope:
    origins = tuple(
        PluginOrigin(
            source=src,  # type: ignore[arg-type]
            trust=trt,  # type: ignore[arg-type]
            enabled_by="profiles/default.yaml",
            discovered_at=f"entry-{idx}",
        )
        for idx, (src, trt) in enumerate(zip(sources, trusts, strict=True))
    )
    return TrustEnvelope(origins=origins, granted_privileges=privileges)


def test_trust_envelope_empty_singleton() -> None:
    """``empty()`` returns a stable singleton."""
    assert TrustEnvelope.empty() is TrustEnvelope.empty()
    assert TrustEnvelope.empty() is EMPTY_TRUST_ENVELOPE


def test_trust_envelope_empty_singleton_equality() -> None:
    """The singleton is equal to itself."""
    a = TrustEnvelope.empty()
    b = TrustEnvelope.empty()
    assert a == b
    assert hash(a) == hash(b)


def test_trust_envelope_grants_membership_true() -> None:
    """``grants`` returns ``True`` for a held privilege."""
    env = _envelope(privileges=frozenset({"state.read", "state.write"}))
    assert env.grants("state.read") is True
    assert env.grants("state.write") is True


def test_trust_envelope_grants_membership_false() -> None:
    """``grants`` returns ``False`` for an unheld privilege."""
    env = _envelope(privileges=frozenset({"state.read"}))
    assert env.grants("state.write") is False
    assert env.grants("") is False


def test_trust_envelope_grants_does_not_raise() -> None:
    """``grants`` is a pure membership check; no exceptions."""
    env = _envelope()
    # No exception, even for bizarre inputs (membership of frozenset is safe).
    assert env.grants("does.not.exist") is False


def test_trust_envelope_rejects_empty_origins() -> None:
    """An envelope with zero origins has no auditable closure."""
    with pytest.raises(ValueError, match="origins must be non-empty"):
        TrustEnvelope(
            origins=(),
            granted_privileges=frozenset({"state.read"}),
        )


def test_trust_envelope_rejects_empty_privileges() -> None:
    """An envelope with zero privileges fails closed (I-HPC-11)."""
    with pytest.raises(ValueError, match="granted_privileges must be non-empty"):
        _envelope(privileges=frozenset())


def test_trust_envelope_rejects_empty_privilege_string() -> None:
    """Empty-string privileges are not allowed."""
    with pytest.raises(ValueError, match="must not contain empty strings"):
        TrustEnvelope(
            origins=(_origin(),),
            granted_privileges=frozenset({""}),
        )


def test_trust_envelope_frozen() -> None:
    """Frozen dataclass rejects attribute assignment."""
    env = _envelope()
    with pytest.raises(dataclasses.FrozenInstanceError):
        env.origins = ()  # type: ignore[misc]


def test_trust_envelope_rejects_set_input() -> None:
    """Passing a mutable ``set`` is rejected (frozen envelope contract)."""
    with pytest.raises(ValueError, match="must be a frozenset"):
        TrustEnvelope(
            origins=(_origin(),),
            granted_privileges={"state.read", "state.write"},  # type: ignore[arg-type]
        )


def test_trust_envelope_empty_singleton_fails_privilege_check() -> None:
    """Empty singleton grants no real privileges — fail-closed by construction."""
    empty = TrustEnvelope.empty()
    assert empty.grants("state.read") is False
    assert empty.grants("trust.empty") is True  # the synthetic sentinel verb
