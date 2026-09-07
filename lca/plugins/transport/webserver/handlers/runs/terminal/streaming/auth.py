"""JWT mint + verify for the LcaAgentGateway handshake.

Wire invariant (spec §5.4):
  - RS256
  - TTL = 5 minutes (configurable per mint call; default 300 s)
  - payload MUST contain `purpose: "cli-sandbox"`, `sub: <user_id>`,
    `operation_id: <run_id>`
  - `iss` / `aud` are configurable

Keys are loaded from:
  - LCA_JWT_SECRET     — PEM-encoded PKCS8 RSA private key (sign)
  - LCA_JWT_PUBLIC_KEY — PEM-encoded SPKI RSA public key (verify)
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


DEFAULT_TTL_SECONDS = 5 * 60
PURPOSE = "cli-sandbox"
DEFAULT_ISSUER = "lca"
DEFAULT_AUDIENCE = "lca-agent-gateway"


def _load_private_key() -> RSAPrivateKey:
    pem = os.environ.get("LCA_JWT_SECRET")
    if not pem:
        raise InvalidTokenError("LCA_JWT_SECRET not set")
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise InvalidTokenError("LCA_JWT_SECRET is not an RSA private key")
    return key


def _load_public_key() -> RSAPublicKey:
    pem = os.environ.get("LCA_JWT_PUBLIC_KEY")
    if not pem:
        raise InvalidTokenError("LCA_JWT_PUBLIC_KEY not set")
    key = serialization.load_pem_public_key(pem.encode())
    if not isinstance(key, RSAPublicKey):
        raise InvalidTokenError("LCA_JWT_PUBLIC_KEY is not an RSA public key")
    return key


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

    Pass `private_key_pem` for tests; production reads LCA_JWT_SECRET.
    """
    if private_key_pem is None:
        key = _load_private_key()
    else:
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

    if public_key_pem is None:
        key = _load_public_key()
    else:
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
    "mint_user_jwt",
    "verify_user_jwt",
)
