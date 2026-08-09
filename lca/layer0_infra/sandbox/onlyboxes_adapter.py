"""Onlyboxes-backed sandbox — console REST + pythonExec.

Auth: ``Authorization: Bearer <access token>`` against console HTTP.
Execution: ``POST /api/v1/tasks`` capability ``pythonExec`` (stateless) or
``POST /api/v1/sessions`` (run-bound persistent sessions, ADR-0050).

Input files are staged under ``/mnt/data/<name>`` by bootstrap preamble;
products under ``/mnt/data/outputs/`` are harvested via base64 artifact block.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.onlyboxes_bootstrap import (
    CAPABILITY_PYTHON,
    PYTHON_LANGUAGES,
    auth_headers,
    build_wrapped_code,
    parse_exec_response,
    timeout_ms,
    wait_ms,
)
from lca.layer0_infra.sandbox.onlyboxes_session import (
    http_create_session,
    http_destroy_session,
    http_run_in_session,
)
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_log = structlog.get_logger(__name__)


class OnlyboxesSandboxAdapter(Sandbox):
    """HTTP client for Onlyboxes console pythonExec + sessions."""

    name = "onlyboxes-sandbox"

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._client = client

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        if language and language.lower() not in PYTHON_LANGUAGES:
            return SandboxResult(
                success=False,
                exit_code=1,
                error=f"OnlyboxesSandboxAdapter supports python only, got {language!r}",
            )

        invocation_id = str(kwargs.get("invocation_id", "") or "")
        emitter = SandboxStreamEmitter(invocation_id)
        wrapped = build_wrapped_code(code, files)
        t_ms = timeout_ms(timeout_s)
        w_ms = wait_ms(timeout_s)
        body = {
            "capability": CAPABILITY_PYTHON,
            "input": {"code": wrapped, "timeout_ms": t_ms},
            "mode": "sync",
            "wait_ms": w_ms,
            "timeout_ms": t_ms,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout((t_ms / 1000.0) + 15.0))
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/api/v1/tasks",
                    headers=auth_headers(self._access_token),
                    json=body,
                )
            except httpx.HTTPError as exc:
                err = f"Onlyboxes transport error: {type(exc).__name__}: {exc}"
                emitter.emit_stderr(err + "\n")
                return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")

            return parse_exec_response(response, emitter)
        finally:
            if owns_client:
                await client.aclose()

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        return await http_create_session(
            self._base_url,
            self._access_token,
            config or SessionConfig(),
            self._client,
        )

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        if language and language.lower() not in PYTHON_LANGUAGES:
            return SandboxResult(
                success=False,
                exit_code=1,
                error=f"OnlyboxesSandboxAdapter supports python only, got {language!r}",
            )
        files = kwargs.get("files")
        file_map = files if isinstance(files, dict) else None
        invocation_id = str(kwargs.get("invocation_id", "") or "")
        return await http_run_in_session(
            self._base_url,
            self._access_token,
            session_id,
            code,
            language,
            timeout_s,
            self._client,
            invocation_id=invocation_id,
            files=file_map,
        )

    async def destroy_session(self, session_id: str) -> None:
        await http_destroy_session(
            self._base_url,
            self._access_token,
            session_id,
            self._client,
        )
