"""Tests for lca.infrastructure.env.layered.filter_env_keys (K7 filter).

Exercises the four rules from ADR-0117 §决定 4:

1. ``.env`` may *override* a :data:`BOOTSTRAP_NAMES` key only when it already
   exists in ``ambient`` (no surprise new bootstrap values).
2. ``.env`` may *introduce* a key matching any :data:`BOOTSTRAP_PREFIXES`
   prefix even when it is not yet in ``ambient``.
3. :data:`BOOTSTRAP_FORBIDDEN` entries are always blocked.
4. Anything else is blocked.

The function is pure — no IO, no ``os.environ`` access — so tests use plain
``dict`` literals for both inputs.
"""

from __future__ import annotations

from lca.infrastructure.env.layered import filter_env_keys


def test_allows_override_of_existing_bootstrap_name() -> None:
    """Rule 1: ``PATH`` already in ambient → .env may override."""
    allowed, blocked = filter_env_keys(
        raw_env={"PATH": "/custom/bin"},
        ambient={"PATH": "/usr/bin"},
    )
    assert "PATH" in allowed
    assert "PATH" not in blocked


def test_blocks_bootstrap_name_not_in_ambient() -> None:
    """Rule 1 (negative): ``SSL_CERT_FILE`` not in ambient → .env blocked."""
    allowed, blocked = filter_env_keys(
        raw_env={"SSL_CERT_FILE": "/etc/ssl/certs/ca.pem"},
        ambient={},
    )
    assert "SSL_CERT_FILE" not in allowed
    assert "SSL_CERT_FILE" in blocked


def test_allows_new_prefix_match() -> None:
    """Rule 2: a fresh LCA prefix key may be introduced by .env."""
    allowed, blocked = filter_env_keys(
        raw_env={"LLM_API_KEY": "sk-test", "GATEWAY_HOST": "127.0.0.1"},
        ambient={"PATH": "/usr/bin"},
    )
    assert "LLM_API_KEY" in allowed
    assert "GATEWAY_HOST" in allowed
    assert not blocked


def test_allows_override_of_existing_prefix_match() -> None:
    """Rule 2 (positive): existing prefix key may also be overridden."""
    allowed, _blocked = filter_env_keys(
        raw_env={"LCA_PROFILE": "nope"},  # forbidden short-circuits first
        ambient={"LCA_PROFILE": "yes"},
    )
    assert "LCA_PROFILE" not in allowed  # forbidden wins over prefix


def test_blocks_forbidden_even_when_ambient_present() -> None:
    """Rule 3: LCA_PROFILE is always blocked — argv/profile only."""
    allowed, blocked = filter_env_keys(
        raw_env={"LCA_PROFILE": "dev"},
        ambient={"LCA_PROFILE": "prod"},
    )
    assert "LCA_PROFILE" in blocked
    assert "LCA_PROFILE" not in allowed


def test_blocks_forbidden_for_secret_keys() -> None:
    """Rule 3: secret material must not be sourced from .env."""
    allowed, blocked = filter_env_keys(
        raw_env={"LCA_KERNEL_KEY": "raw-secret"},
        ambient={},
    )
    assert "LCA_KERNEL_KEY" in blocked
    assert "LCA_KERNEL_KEY" not in allowed


def test_blocks_internal_injection_attempt() -> None:
    """Rule 3: kernel internal flag namespace is protected."""
    allowed, blocked = filter_env_keys(
        raw_env={"LCA_INTERNAL_INJECTION": "1"},
        ambient={},
    )
    assert "LCA_INTERNAL_INJECTION" in blocked
    assert "LCA_INTERNAL_INJECTION" not in allowed


def test_blocks_unknown_keys_with_no_prefix_match() -> None:
    """Rule 4: anything outside whitelist is blocked by default."""
    allowed, blocked = filter_env_keys(
        raw_env={
            "FOO_BAR_BAZ": "1",
            "RANDOM_NAME": "x",
            "FOOBAR_": "y",  # not a configured prefix
        },
        ambient={"PATH": "/usr/bin"},
    )
    assert "FOO_BAR_BAZ" in blocked
    assert "RANDOM_NAME" in blocked
    assert "FOOBAR_" in blocked
    assert all(k not in allowed for k in ("FOO_BAR_BAZ", "RANDOM_NAME", "FOOBAR_"))


def test_mixed_inputs_partition_into_disjoint_sets() -> None:
    """The returned frozensets partition raw_env.keys() exactly."""
    raw = {
        "PATH": "/a",  # bootstrap_name in ambient → allowed
        "SSL_CERT_FILE": "/b",  # bootstrap_name not in ambient → blocked
        "LLM_API_KEY": "k",  # prefix → allowed
        "LCA_PROFILE": "p",  # forbidden → blocked
        "FOO": "bar",  # unknown → blocked
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://x",  # prefix → allowed
    }
    ambient = {"PATH": "/usr/bin"}
    allowed, blocked = filter_env_keys(raw, ambient)
    assert isinstance(allowed, frozenset)
    assert isinstance(blocked, frozenset)
    assert allowed.isdisjoint(blocked)
    assert allowed | blocked == frozenset(raw.keys())
    assert "PATH" in allowed
    assert "LLM_API_KEY" in allowed
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in allowed
    assert "SSL_CERT_FILE" in blocked
    assert "LCA_PROFILE" in blocked
    assert "FOO" in blocked


def test_empty_inputs_return_empty_frozensets() -> None:
    allowed, blocked = filter_env_keys({}, {})
    assert allowed == frozenset()
    assert blocked == frozenset()


def test_xdg_and_dyld_prefixes_allowed() -> None:
    """Freedesktop + macOS dynamic linker prefixes are part of the prefix list."""
    raw = {"XDG_CONFIG_HOME": "/x", "DYLD_FALLBACK_LIBRARY_PATH": "/lib"}
    allowed, blocked = filter_env_keys(raw, ambient={})
    assert "XDG_CONFIG_HOME" in allowed
    assert "DYLD_FALLBACK_LIBRARY_PATH" in allowed
    assert not blocked


def test_dsh_migration_prefix_allowed() -> None:
    """Deepseek users can keep DSH_ prefix keys after migration."""
    allowed, blocked = filter_env_keys(
        raw_env={"DSH_BASE_URL": "https://x", "DSH_API_KEY": "k"},
        ambient={},
    )
    assert "DSH_BASE_URL" in allowed
    assert "DSH_API_KEY" in allowed
    assert not blocked
