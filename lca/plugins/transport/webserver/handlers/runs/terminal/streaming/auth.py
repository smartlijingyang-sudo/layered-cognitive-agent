"""JWT mint + verify for the LcaAgentGateway handshake.

Wire invariant (spec §5.4):
  - RS256
  - TTL = 5 minutes (configurable per mint call; default 300 s)
  - payload MUST contain `purpose: "cli-sandbox"`, `sub: <user_id>`,
    `operation_id: <run_id>`
  - `iss` / `aud` are configurable

Keys are passed in explicitly via the ``jwt_keys`` seam
(:mod:`lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys`) — this module
no longer reads ``os.environ`` directly (AGENTS §4).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)


class InvalidTokenError(Exception):
    """Token missing, malformed, expired, or signed with the wrong key."""


class JwtSecretUnconfiguredError(InvalidTokenError):
    """Profile did not inject the JWT signing key.

    The webserver handler that builds the run receipt must translate this
    into a 503 ``jwt_secret_unconfigured`` response rather than letting it
    surface as a generic 500 — see ``docs/notes/jwt-secret-injection-via-profile.md``.
    """


DEFAULT_TTL_SECONDS = 5 * 60
PURPOSE = "cli-sandbox"
DEFAULT_ISSUER = "lca"
DEFAULT_AUDIENCE = "lca-agent-gateway"

# Legacy fallback: read LCA_JWT_SECRET / LCA_JWT_PUBLIC_KEY directly from the
# process environment when the caller did not pass an explicit PEM. Plugin
# handlers in transport/webserver always obtain the key through the
# `jwt_keys` capability (see lca-webserver-jwt-keys), so this fallback only
# fires in tests and ad-hoc scripts. A one-shot warning is logged the first
# time it triggers so the violation stays visible.
_env_fallback_warned = {"private": False, "public": False}


def _env_fallback(name: str) -> str | None:
    import warnings

    pem = os.environ.get(name)
    if pem and not _env_fallback_warned["private" if name == "LCA_JWT_SECRET" else "public"]:
        warnings.warn(
            f"{name} read directly from os.environ; this is the legacy fallback. "
            "Plugin code should pass `private_key_pem` / `public_key_pem` "
            "explicitly from the `jwt_keys` capability instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        _env_fallback_warned["private" if name == "LCA_JWT_SECRET" else "public"] = True
    return pem


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    import base64

    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _canonical(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def mint_user_jwt(
    *,
    user_id: str,
    operation_id: str,
    private_key_pem: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_AUDIENCE,
    issued_at: int | None = None,
) -> str:
    """Mint a JWT for the WS handshake.

    Production callers must pass ``private_key_pem`` explicitly — the
    webserver handler chain reads it from ``app.state.jwt_keys`` (installed
    by ``lca-webserver-bootstrap`` from the ``jwt_keys`` capability; see
    :mod:`lca.plugins.transport.webserver.jwt_keys_seam`). When the key is
    missing AND ``LCA_JWT_SECRET`` is also unset, this raises
    :class:`JwtSecretUnconfiguredError`, which the command-endpoint handler
    translates into a 503 ``jwt_secret_unconfigured`` response.

    The ``LCA_JWT_SECRET`` env-var fallback only fires for tests / ad-hoc
    scripts that have not migrated to the ``jwt_keys`` capability; a one-shot
    DeprecationWarning is logged the first time it triggers.
    """
    if not private_key_pem:
        private_key_pem = _env_fallback("LCA_JWT_SECRET")
    if not private_key_pem:
        raise JwtSecretUnconfiguredError(
            "JWT signing key is not configured; ensure the active Profile provides "
            "`jwt.private_pem` (or `{from_env: LCA_JWT_SECRET}`) or enable "
            "`jwt.dev_mode: true` for local development."
        )
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("private_key_pem is not an RSA private key")

    now = issued_at if issued_at is not None else int(time.time())
    payload = {
        "sub": user_id,
        "operation_id": operation_id,
        "purpose": PURPOSE,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "nbf": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = (
        _b64url(_canonical(header)).encode() + b"." + _b64url(_canonical(payload)).encode()
    )
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return signing_input.decode("ascii") + "." + _b64url(signature)


def verify_user_jwt(
    token: str,
    *,
    expected_operation_id: str | None = None,
    public_key_pem: str | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify a JWT; return the decoded payload.

    Raises :class:`InvalidTokenError` on any failure. Distinguishes
    expired tokens (raises with code='expired') from invalid signatures
    so the gateway can return `auth_expired` vs `auth_failed`.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("empty token")
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("malformed token")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = (header_b64 + "." + payload_b64).encode()
    try:
        signature = _b64url_decode(sig_b64)
    except Exception as exc:
        raise InvalidTokenError(f"bad signature encoding: {exc}") from exc

    if not public_key_pem:
        public_key_pem = _env_fallback("LCA_JWT_PUBLIC_KEY")
    if not public_key_pem:
        raise JwtSecretUnconfiguredError(
            "JWT verification key is not configured; ensure the active Profile "
            "provides `jwt.public_pem` (or `{from_env: LCA_JWT_PUBLIC_KEY}`)."
        )
    key = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(key, RSAPublicKey):
        raise InvalidTokenError("public_key_pem is not an RSA public key")

    try:
        key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise InvalidTokenError("signature mismatch") from exc

    try:
        header = __import__("json").loads(_b64url_decode(header_b64))
        payload = __import__("json").loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise InvalidTokenError(f"bad payload: {exc}") from exc

    if header.get("alg") != "RS256":
        raise InvalidTokenError(f"unsupported alg: {header.get('alg')}")
    if payload.get("purpose") != PURPOSE:
        raise InvalidTokenError(f"wrong purpose: {payload.get('purpose')!r}")
    if expected_operation_id is not None and payload.get("operation_id") != expected_operation_id:
        raise InvalidTokenError("operation_id mismatch")

    current = now if now is not None else int(time.time())
    if int(payload.get("exp", 0)) < current:
        raise InvalidTokenError("token expired")
    if int(payload.get("nbf", current + 1)) > current:
        raise InvalidTokenError("token not yet valid")
    return payload


__all__ = (
    "DEFAULT_TTL_SECONDS",
    "InvalidTokenError",
    "JwtSecretUnconfiguredError",
    "mint_user_jwt",
    "verify_user_jwt",
)
