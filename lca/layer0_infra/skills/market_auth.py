"""Resolve LobeHub Market Bearer tokens for skill search.

Auth priority (first hit wins):
1. ``LCA_SKILL_MARKET_TOKEN`` — static Bearer (dev / CI)
2. M2M client credentials — ``LCA_SKILL_MARKET_CLIENT_ID`` / ``_SECRET``,
   or ``MARKET_CLIENT_ID`` / ``MARKET_CLIENT_SECRET``,
   or ``~/.lobehub-market/credentials.json`` (same file as ``@lobehub/market-cli register``)

M2M uses OAuth2 client_credentials + JWT client assertion (HS256), matching
``@lobehub/market-sdk`` ``fetchM2MToken``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from lca.layer0_infra.skills.settings import SkillSettings, get_skill_settings

_DEFAULT_CREDENTIALS_PATH = Path.home() / ".lobehub-market" / "credentials.json"
_TOKEN_SKEW_S = 60
_ASSERTION_TTL_S = 300


@dataclass(frozen=True)
class _CachedToken:
    access_token: str
    expires_at_monotonic: float


_cache: _CachedToken | None = None


def clear_market_token_cache() -> None:
    """Drop cached access token (tests / credential rotation)."""
    global _cache
    _cache = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_client_assertion(
    *,
    client_id: str,
    client_secret: str,
    token_endpoint: str,
    now: int | None = None,
) -> str:
    """Build HS256 JWT client assertion for Market OAuth token exchange."""
    issued_at = int(time.time()) if now is None else now
    header = _b64url(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload = _b64url(
        json.dumps(
            {
                "iss": client_id,
                "sub": client_id,
                "aud": token_endpoint,
                "jti": str(uuid.uuid4()),
                "iat": issued_at,
                "exp": issued_at + _ASSERTION_TTL_S,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(
        client_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def _read_credentials_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def resolve_m2m_credentials(
    settings: SkillSettings | None = None,
) -> tuple[str, str, str] | None:
    """Return ``(client_id, client_secret, base_url)`` or None."""
    cfg = settings if settings is not None else get_skill_settings()
    base_url = (cfg.market_base_url or "https://market.lobehub.com").rstrip("/")

    client_id = (cfg.market_client_id or "").strip() or (
        os.environ.get("MARKET_CLIENT_ID") or ""
    ).strip()
    client_secret = (cfg.market_client_secret or "").strip() or (
        os.environ.get("MARKET_CLIENT_SECRET") or ""
    ).strip()
    if client_id and client_secret:
        return client_id, client_secret, base_url

    cred_path = cfg.market_credentials_path or _DEFAULT_CREDENTIALS_PATH
    file_creds = _read_credentials_file(Path(cred_path))
    if not file_creds:
        return None
    file_id = str(file_creds.get("clientId") or file_creds.get("client_id") or "").strip()
    file_secret = str(
        file_creds.get("clientSecret") or file_creds.get("client_secret") or ""
    ).strip()
    if not file_id or not file_secret:
        return None
    file_base = str(file_creds.get("baseUrl") or file_creds.get("base_url") or "").strip()
    if file_base:
        base_url = file_base.rstrip("/")
    return file_id, file_secret, base_url


def token_endpoint_for(base_url: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", "oauth/token")


async def exchange_m2m_token(
    *,
    client_id: str,
    client_secret: str,
    base_url: str,
    timeout_s: float = 60.0,
) -> tuple[str, int]:
    """Exchange client credentials for ``(access_token, expires_in)``."""
    endpoint = token_endpoint_for(base_url)
    assertion = create_client_assertion(
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=endpoint,
    )
    data = {
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion,
    }
    timeout = httpx.Timeout(timeout_s)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(
            endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Market M2M token HTTP {response.status_code}: {response.text[:300]}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Market M2M token response is not an object")
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Market M2M token missing access_token: {payload!r}"[:300])
    expires_raw = payload.get("expires_in", 3600)
    try:
        expires_in = int(expires_raw)
    except (TypeError, ValueError):
        expires_in = 3600
    return token, max(expires_in, 60)


async def resolve_market_access_token(
    settings: SkillSettings | None = None,
    *,
    force_refresh: bool = False,
) -> str | None:
    """Return a usable Bearer access token, or None if no auth configured."""
    global _cache
    cfg = settings if settings is not None else get_skill_settings()

    static = (cfg.market_token or "").strip()
    if static:
        return static

    if not force_refresh and _cache is not None and time.monotonic() < _cache.expires_at_monotonic:
        return _cache.access_token

    m2m = resolve_m2m_credentials(cfg)
    if m2m is None:
        return None
    client_id, client_secret, base_url = m2m
    try:
        token, expires_in = await exchange_m2m_token(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            timeout_s=cfg.market_timeout_s,
        )
    except (RuntimeError, httpx.HTTPError):
        return None

    _cache = _CachedToken(
        access_token=token,
        expires_at_monotonic=time.monotonic() + max(expires_in - _TOKEN_SKEW_S, 30),
    )
    return token


def market_auth_setup_hint() -> str:
    """Operator-facing text when search cannot authenticate."""
    return (
        "Market 搜索需要鉴权。任选其一：\n"
        "1) 一次性注册（推荐，与 @lobehub/market-cli 共用凭证）:\n"
        "   npx -y @lobehub/market-cli register "
        '--name "LCA-Agent" --description "Layered Cognitive Agent" --source lca\n'
        "   凭证写入 ~/.lobehub-market/credentials.json，LCA 会自动读取并换取 access token。\n"
        "2) 设置 LCA_SKILL_MARKET_CLIENT_ID + LCA_SKILL_MARKET_CLIENT_SECRET\n"
        "3) 或直接设置 LCA_SKILL_MARKET_TOKEN（静态 Bearer）\n"
        "无鉴权时仍可用 import_skill(identifier=... 或 url=...) 直接安装。"
    )
