"""Onlyboxes session HTTP operations.

Separated from ``onlyboxes_adapter`` to keep both files under the line-count
threshold.  The adapter delegates session methods here.
"""

from __future__ import annotations

import base64
import json

import httpx
import structlog

from lca.contracts.models.core.sandbox import (
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.layer0_infra.sandbox.onlyboxes_bootstrap import (
    PYTHON_LANGUAGES,
    auth_headers,
    parse_exec_response,
    safe_rel_name,
    timeout_ms,
)
from lca.layer0_infra.sandbox.onlyboxes_session_bootstrap import build_session_wrapped_code
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_log = structlog.get_logger(__name__)


async def http_create_session(
    base_url: str,
    access_token: str,
    config: SessionConfig,
    client: httpx.AsyncClient | None,
) -> SessionInfo | None:
    """POST /api/v1/sessions → SessionInfo or None on failure."""
    t_ms = timeout_ms(config.timeout_s)
    mounts: list[dict[str, str]] = []
    for raw_name, data in config.files.items():
        name = safe_rel_name(raw_name)
        mounts.append({"name": name, "b64": base64.b64encode(data).decode("ascii")})

    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(t_ms / 1000.0 + 15.0))
    try:
        resp = await client.post(
            f"{base_url}/api/v1/sessions",
            headers=auth_headers(access_token),
            json={"timeout_ms": t_ms, "mounts": mounts},
        )
        if resp.status_code >= 400:
            _log.debug("session_create_failed", status=resp.status_code, body=resp.text[:200])
            return None
        payload = resp.json()
        return SessionInfo(
            session_id=str(payload["session_id"]),
            container_id=str(payload.get("container_id", "")),
        )
    except (httpx.HTTPError, KeyError, json.JSONDecodeError):
        _log.debug("session_create_error", exc_info=True)
        return None
    finally:
        if owns:
            await client.aclose()


async def http_run_in_session(
    base_url: str,
    access_token: str,
    session_id: str,
    code: str,
    language: str,
    timeout_s: int,
    client: httpx.AsyncClient | None,
    invocation_id: str = "",
    files: dict[str, bytes] | None = None,
) -> SandboxResult:
    """POST /api/v1/sessions/{id}/exec → SandboxResult."""
    if language and language.lower() not in PYTHON_LANGUAGES:
        return SandboxResult(
            success=False,
            exit_code=1,
            error=f"OnlyboxesSandboxAdapter supports python only, got {language!r}",
        )

    emitter = SandboxStreamEmitter(invocation_id)
    wrapped = build_session_wrapped_code(code, files)
    t_ms = timeout_ms(timeout_s)

    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(t_ms / 1000.0 + 15.0))
    try:
        try:
            resp = await client.post(
                f"{base_url}/api/v1/sessions/{session_id}/exec",
                headers=auth_headers(access_token),
                json={"code": wrapped, "timeout_ms": t_ms},
            )
        except httpx.HTTPError as exc:
            err = f"Onlyboxes session transport error: {type(exc).__name__}: {exc}"
            emitter.emit_stderr(err + "\n")
            return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")
        return parse_exec_response(resp, emitter)
    finally:
        if owns:
            await client.aclose()


async def http_destroy_session(
    base_url: str,
    access_token: str,
    session_id: str,
    client: httpx.AsyncClient | None,
) -> None:
    """DELETE /api/v1/sessions/{id}. Idempotent."""
    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        await client.delete(
            f"{base_url}/api/v1/sessions/{session_id}",
            headers=auth_headers(access_token),
        )
    except httpx.HTTPError:
        _log.debug("session_destroy_error", session_id=session_id, exc_info=True)
    finally:
        if owns:
            await client.aclose()
