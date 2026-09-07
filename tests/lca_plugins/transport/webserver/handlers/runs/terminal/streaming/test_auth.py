"""Regression tests for ``handlers/runs/terminal/streaming/auth.py``.

The contract under test:

1. ``mint_user_jwt`` requires ``private_key_pem`` and raises
   :class:`JwtSecretUnconfiguredError` (subclass of
   :class:`InvalidTokenError`) when it is empty — the handler chain
   translates that into a 503 ``jwt_secret_unconfigured`` response.
2. ``verify_user_jwt`` requires ``public_key_pem`` and raises
   :class:`JwtSecretUnconfiguredError` when it is empty.
3. ``mint_user_jwt`` with a real PEM produces a JWT that
   ``verify_user_jwt`` accepts and that distinguishes ``purpose``.
4. The module no longer reads ``os.environ`` directly (AGENTS §4).
   Verified indirectly: passing empty PEM is the only way to trigger
   the unconfigured error, regardless of what env vars are set.
"""

from __future__ import annotations

import time

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
