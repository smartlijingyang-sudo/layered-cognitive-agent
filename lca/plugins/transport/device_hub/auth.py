"""Token verification for device connections and HTTP routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

from lca.plugins.transport.device_hub.settings import DeviceHubSettings


class AuthError(Exception):
    """Invalid or unknown token."""


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    workspace_id: str | None
    token_type: str


def verify_token(
    token: str,
    token_type: str,
    settings: DeviceHubSettings,
) -> AuthenticatedUser:
    kind = (token_type or "serviceToken").strip()
    if kind == "serviceToken":
        if not settings.service_token or not hmac.compare_digest(token, settings.service_token):
            raise AuthError("Invalid service token")
        return AuthenticatedUser(
            user_id=settings.subject,
            workspace_id=None,
            token_type="serviceToken",  # noqa: S106
        )
    if kind == "jwt":
        return _verify_jwt(token, settings)
    if kind == "apiKey":
        if token and token in settings.api_keys:
            return AuthenticatedUser(
                user_id="api-key-user",
                workspace_id=None,
                token_type="apiKey",  # noqa: S106
            )
        raise AuthError("apiKey auth is not configured")
    raise AuthError(f"Unknown token type: {kind}")


def _verify_jwt(token: str, settings: DeviceHubSettings) -> AuthenticatedUser:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Malformed JWT")
    header_b64, payload_b64, signature_b64 = parts
    if settings.jwt_secret:
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
        try:
            given = _b64url_decode(signature_b64)
        except ValueError as exc:
            raise AuthError("Malformed JWT signature") from exc
        if not hmac.compare_digest(expected, given):
            raise AuthError("Invalid JWT signature")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Malformed JWT payload") from exc
    if not isinstance(payload, dict):
        raise AuthError("Malformed JWT payload")
    exp = payload.get("exp")
    if exp is not None:
        import time as _time

        try:
            if float(exp) < _time.time():
                raise AuthError("JWT expired")
        except (TypeError, ValueError) as exc:
            raise AuthError("JWT exp is not a number") from exc
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise AuthError("JWT missing sub")
    workspace = payload.get("workspace_id")
    return AuthenticatedUser(
        user_id=user_id,
        workspace_id=str(workspace) if workspace else None,
        token_type="jwt",  # noqa: S106
    )


def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))
