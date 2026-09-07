"""Regression tests for ``handlers/runs/terminal/streaming/auth.py``.

The contract under test:

1. ``mint_user_jwt`` requires ``private_key_pem`` and raises
   :class:`JwtSecretUnconfiguredError` (subclass of
   :class:`InvalidTokenError`) when both the explicit PEM and the
   ``LCA_JWT_SECRET`` env-var fallback are empty — the handler chain
   translates that into a 503 ``jwt_secret_unconfigured`` response.
2. ``verify_user_jwt`` requires ``public_key_pem`` and raises
   :class:`JwtSecretUnconfiguredError` when both the explicit PEM and
   the ``LCA_JWT_PUBLIC_KEY`` env-var fallback are empty.
3. ``mint_user_jwt`` with a real PEM produces a JWT that
   ``verify_user_jwt`` accepts and that distinguishes ``purpose``.
4. Env-var fallback fires a one-shot ``DeprecationWarning`` so the
   violation of AGENTS §4 stays visible without breaking tests / scripts
   that have not migrated.
"""

from __future__ import annotations

import time
import warnings

import pytest

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError,
    JwtSecretUnconfiguredError,
    mint_user_jwt,
    verify_user_jwt,
)
from lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys import (
    generate_dev_keypair,
)


@pytest.fixture(autouse=True)
def _scrub_jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the env-var fallback to be unavailable unless the test opts in.

    Most contract assertions want explicit PEM only; the env fallback is
    covered separately by ``test_env_fallback_*``.
    """
    monkeypatch.delenv("LCA_JWT_SECRET", raising=False)
    monkeypatch.delenv("LCA_JWT_PUBLIC_KEY", raising=False)
    # Reset the one-shot warning guard so each test can re-assert it.
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming import (
        auth,
    )

    auth._env_fallback_warned["private"] = False
    auth._env_fallback_warned["public"] = False


def test_mint_user_jwt_rejects_empty_private_pem() -> None:
    with pytest.raises(JwtSecretUnconfiguredError):
        mint_user_jwt(user_id="u", operation_id="op", private_key_pem="")
    # The new error must remain a subclass of InvalidTokenError so the
    # existing call-sites that catch InvalidTokenError still work.
    with pytest.raises(InvalidTokenError):
        mint_user_jwt(user_id="u", operation_id="op", private_key_pem="")


def test_verify_user_jwt_rejects_empty_public_pem() -> None:
    token = mint_user_jwt(
        user_id="u",
        operation_id="op",
        private_key_pem=generate_dev_keypair()[0],
    )
    with pytest.raises(JwtSecretUnconfiguredError):
        verify_user_jwt(token, public_key_pem="")


def test_mint_and_verify_roundtrip() -> None:
    priv, pub = generate_dev_keypair()
    now = int(time.time())
    token = mint_user_jwt(
        user_id="alice",
        operation_id="op-42",
        private_key_pem=priv,
        ttl_seconds=60,
        issued_at=now,
    )
    payload = verify_user_jwt(
        token,
        public_key_pem=pub,
        expected_operation_id="op-42",
        now=now + 5,
    )
    assert payload["sub"] == "alice"
    assert payload["purpose"] == "cli-sandbox"
    assert payload["operation_id"] == "op-42"


def test_verify_rejects_tampered_signature() -> None:
    priv, pub = generate_dev_keypair()
    token = mint_user_jwt(user_id="u", operation_id="op", private_key_pem=priv)
    tampered = token[:-2] + ("AB" if token[-2:] != "AB" else "CD")
    with pytest.raises(InvalidTokenError, match="signature"):
        verify_user_jwt(tampered, public_key_pem=pub)


def test_env_fallback_warns_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LCA_JWT_SECRET is set and no explicit PEM is passed, the
    fallback fires and emits a single DeprecationWarning.
    """
    priv, _pub = generate_dev_keypair()
    monkeypatch.setenv("LCA_JWT_SECRET", priv)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        token = mint_user_jwt(user_id="u", operation_id="op")

    deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation) == 1
    assert "LCA_JWT_SECRET" in str(deprecation[0].message)
    assert token.count(".") == 2

    # Second call: warning suppressed (one-shot guard).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mint_user_jwt(user_id="u", operation_id="op")
    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []
