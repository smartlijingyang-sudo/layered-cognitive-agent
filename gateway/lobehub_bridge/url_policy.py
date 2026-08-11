"""SSRF guard for LobeHub file ingest HTTP(S) downloads."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from gateway.lobehub_bridge.settings import LobeHubBridgeSettings, bridge_settings

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class IngestUrlPolicyError(Exception):
    """Raised when a remote URL is not permitted by ingest policy."""


def assert_ingest_url_allowed(
    url: str,
    settings: LobeHubBridgeSettings | None = None,
) -> None:
    """Validate ``url`` before outbound fetch (data URIs bypass this check)."""
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

    if cfg.ingest_allow_private_ip and _is_private_or_loopback(host):
        return

    raise IngestUrlPolicyError(f"host not allowed for ingest: {host}")


def _is_private_or_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)
