"""Company file-service client for the ``POST /files`` upload seam.

The company file service stores the bytes and returns the canonical remote URL
(``source``). It can also mint a short-lived authorized link (``valid``), which
LCA never persists: the bytes are already local by the time we call it, so the
expiring projection has no consumer here.

Wire contract (agreed 2026-11-18)::

    POST {base}/upload?appId=&pwd=&needView=0   multipart, repeated field "files"
    -> {"code": "200", "msg": "...", "data": {"files": ["<source>", ...]}}

``needView=0`` makes ``data.files`` a **string array**. With ``needView=1`` the
same field becomes an object array, which this client rejects as a contract
violation rather than guessing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

_log = logging.getLogger(__name__)

_UPLOAD_PATH = "/upload"
_NEED_VIEW_NONE = "0"
_TIMEOUT_S = 120.0


class FileServiceError(RuntimeError):
    """Base error for company file-service calls."""


class FileServiceUnavailableError(FileServiceError):
    """Transport failure: unreachable host, timeout, or non-2xx HTTP status."""


class FileServiceContractViolationError(FileServiceError):
    """Response shape or item count does not match the agreed contract."""


@dataclass(frozen=True)
class FileServiceSettings:
    """Resolved credentials. Empty fields mean "not configured"."""

    base_url: str = ""
    app_id: str = ""
    pwd: str = ""
    timeout_s: float = _TIMEOUT_S

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip() and self.app_id.strip() and self.pwd.strip())


def redact_url(url: str) -> str:
    """Drop the query string so credentials never reach logs or traces."""
    return url.split("?", 1)[0]


def parse_upload_response(payload: Any, *, expected: int) -> list[str]:
    """Validate a ``needView=0`` upload response and return the source URLs.

    Fails loud on every deviation: the caller gets an explicit contract
    violation instead of a silently mismatched filename/source pairing.
    """
    if not isinstance(payload, dict):
        raise FileServiceContractViolationError("fileservice response is not a JSON object")
    code = payload.get("code")
    if str(code) != "200":
        msg = payload.get("msg")
        raise FileServiceError(f"fileservice code={code!r} msg={msg!r}")
    data = payload.get("data")
    raw = data.get("files") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise FileServiceContractViolationError("fileservice data.files is not a list")
    sources: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise FileServiceContractViolationError(
                "fileservice data.files items must be non-empty strings (needView=0)"
            )
        sources.append(item.strip())
    if len(sources) != expected:
        raise FileServiceContractViolationError(
            f"fileservice returned {len(sources)} sources for {expected} files"
        )
    return sources


class FileServiceClient:
    """Upload files to the company file service. Stateless and reusable."""

    def __init__(self, settings: FileServiceSettings) -> None:
        self._settings = settings

    async def upload_sources(self, files: Sequence[tuple[str, bytes, str]]) -> list[str]:
        """Upload ``(name, data, mime)`` items once and return their source URLs."""
        if not files:
            return []
        url = f"{self._settings.base_url.rstrip('/')}{_UPLOAD_PATH}"
        params = {
            "appId": self._settings.app_id,
            "pwd": self._settings.pwd,
            "needView": _NEED_VIEW_NONE,
        }
        multipart = [
            ("files", (name, data, mime or "application/octet-stream"))
            for name, data, mime in files
        ]
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._settings.timeout_s)) as client:
                response = await client.post(url, params=params, files=multipart)
                response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            # ``str(exc)`` echoes the request URL, credentials included: log the
            # exception type only.
            _log.warning(
                "fileservice.upload.unavailable path=%s exc_type=%s",
                redact_url(url),
                type(exc).__name__,
            )
            raise FileServiceUnavailableError(
                f"company file service unreachable: {type(exc).__name__}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FileServiceContractViolationError("fileservice response is not JSON") from exc
        sources = parse_upload_response(payload, expected=len(files))
        _log.info("fileservice.upload.ok count=%d", len(sources))
        return sources
