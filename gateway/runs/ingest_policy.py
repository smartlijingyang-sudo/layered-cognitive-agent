"""Authorize remote URLs before the ingest transport opens an outbound connection."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from gateway.runs.ingest_models import (
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
    bridge_settings,
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def assert_ingest_url_allowed(
    url: str,
    settings: LobeHubBridgeSettings | None = None,
) -> None:
    """Fail closed unless an HTTP(S) URL targets an explicitly allowed host."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise IngestUrlPolicyError(f"unsupported URL scheme: {scheme or '(empty)'}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise IngestUrlPolicyError("URL missing hostname")
    cfg = settings if settings is not None else bridge_settings()
    if host in cfg.allowed_hosts():
        return
    if cfg.ingest_allow_private_ip and is_private_or_loopback(host):
        return
    raise IngestUrlPolicyError(f"host not allowed for ingest: {host}")


def is_private_or_loopback(host: str) -> bool:
    """Return whether a literal host is loopback, RFC1918, or link-local."""
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


__all__ = ["assert_ingest_url_allowed", "is_private_or_loopback"]
