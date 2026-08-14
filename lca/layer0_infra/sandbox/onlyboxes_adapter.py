"""Onlyboxes-backed sandbox — unified terminalExec channel.

Auth: ``Authorization: Bearer <access token>`` against console HTTP.
Execution: all operations go through ``POST /api/v1/commands/terminal``
(aligned with LobeHub ``execTerminal`` pattern).

File writing uses two strategies:
- URL strings → ``curl -fsSL <url> -o <path>``
- Binary data → 48 KB base64 chunks via ``printf '%s' '<b64>' | base64 -d >> '<path>'``

Code execution writes source to ``/tmp/lca-code-<id>.<ext>`` then runs the
appropriate interpreter, avoiding ``ARG_MAX`` crashes from inline base64.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import structlog

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.guest_layout import GuestLayout
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.bootstrap import SANDBOX_FILES_INIT_MARKER
from lca.layer0_infra.sandbox.onlyboxes_bootstrap import (
    auth_headers,
    parse_terminal_response,
    safe_rel_name,
    timeout_ms,
)
from lca.layer0_infra.sandbox.paths import ONLYBOXES
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_log = structlog.get_logger(__name__)

# ── constants ───────────────────────────────────────────────────────

WRITE_CHUNK_BYTES: int = 48 * 1024
DEFAULT_LEASE_TTL_SEC: int = 900

_TERMINAL_ENDPOINT: str = "/api/v1/commands/terminal"

_LANG_EXTENSION: dict[str, str] = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
}
_LANG_RUNNER: dict[str, str] = {
    "python": "python3",
    "javascript": "node",
    "typescript": "npx --yes tsx",
}
_DEFAULT_EXTENSION: str = "py"
_DEFAULT_RUNNER: str = "python3"


class OnlyboxesSandboxAdapter(Sandbox):
    """HTTP client for Onlyboxes console — unified terminalExec channel."""

    name = "onlyboxes-sandbox"

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        client: httpx.AsyncClient | None = None,
        layout: GuestLayout | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._client = client
        self._lease_ttl_sec = DEFAULT_LEASE_TTL_SEC
        self._layout = layout if layout is not None else ONLYBOXES

    # ── internal: terminal execution ────────────────────────────────

    async def _exec_terminal(
        self,
        command: str,
        *,
        session_id: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
    ) -> SandboxResult:
        """Unified terminal execution channel — aligned with LobeHub execTerminal."""
        emitter = SandboxStreamEmitter(invocation_id)
        t_ms = timeout_ms(timeout_s)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout((t_ms / 1000.0) + 15.0),
        )
        try:
            body = {
                "command": self._layout.with_cwd(command),
                "create_if_missing": True,
                "lease_ttl_sec": self._lease_ttl_sec,
                "session_id": session_id,
                "timeout_ms": t_ms,
            }
            try:
                response = await client.post(
                    f"{self._base_url}{_TERMINAL_ENDPOINT}",
                    headers=auth_headers(self._access_token),
                    json=body,
                )
            except httpx.HTTPError as exc:
                err = f"Onlyboxes transport error: {type(exc).__name__}: {exc}"
                emitter.emit_stderr(err + "\n")
                return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")

            return parse_terminal_response(response, emitter)
        finally:
            if owns_client:
                await client.aclose()

    # ── internal: file writing helpers ──────────────────────────────

    async def _write_text_file(
        self,
        content: str,
        path: str,
        *,
        session_id: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> None:
        """Write text content to *path* via base64 chunking."""
        data = content.encode("utf-8")
        await self._write_file_chunked(data, path, session_id, timeout_s=timeout_s)

    async def _write_file_chunked(
        self,
        data: bytes,
        path: str,
        session_id: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> None:
        """Write binary data to *path* in base64-encoded chunks."""
        # Truncate target and ensure parent directory exists.
        await self._exec_terminal(
            f"mkdir -p \"$(dirname '{path}')\" && : > '{path}'",
            session_id=session_id,
            timeout_s=timeout_s,
        )
        for offset in range(0, max(len(data), 1), WRITE_CHUNK_BYTES):
            chunk = base64.b64encode(data[offset : offset + WRITE_CHUNK_BYTES]).decode("ascii")
            await self._exec_terminal(
                f"printf '%s' '{chunk}' | base64 -d >> '{path}'",
                session_id=session_id,
                timeout_s=timeout_s,
            )

    # ── Sandbox protocol: write_files ───────────────────────────────

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> SandboxResult:
        """Write files to sandbox disk.

        * ``str`` values starting with ``http(s)://`` → ``curl`` download.
        * ``bytes`` values → 48 KB base64-chunked write.
        """
        curl_cmds: list[str] = []
        chunk_files: list[tuple[str, bytes, str]] = []
        root = base_dir or self._layout.root

        for name, source in files.items():
            path = f"{root}/{safe_rel_name(name)}"
            if isinstance(source, str) and source.startswith(("http://", "https://")):
                curl_cmds.append(f"curl -fsSL '{source}' -o '{path}'")
            else:
                raw = source if isinstance(source, bytes) else source.encode("utf-8")
                chunk_files.append((name, raw, path))

        # Batch curl downloads in a single terminal call with idempotency marker.
        if curl_cmds:
            marker = SANDBOX_FILES_INIT_MARKER
            joined = " && ".join(curl_cmds)
            cmd = (
                f"mkdir -p '{root}'; if [ ! -f '{marker}' ]; then {joined} && touch '{marker}'; fi"
            )
            result = await self._exec_terminal(cmd, session_id=session_id, timeout_s=timeout_s)
            if not result.success:
                return result

        # Chunked binary writes.
        for _name, data, path in chunk_files:
            await self._write_file_chunked(data, path, session_id, timeout_s=timeout_s)

        return SandboxResult(success=True, exit_code=0)

    # ── Sandbox protocol: run ───────────────────────────────────────

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        """Execute code by writing to a temp file then running the interpreter."""
        lang_key = language.lower() if language else "python"
        ext = _LANG_EXTENSION.get(lang_key, _DEFAULT_EXTENSION)
        runner = _LANG_RUNNER.get(lang_key, _DEFAULT_RUNNER)

        code_path = f"/tmp/lca-code-{new_id('code')}.{ext}"  # noqa: S108
        await self._write_text_file(code, code_path, session_id="", timeout_s=timeout_s)
        return await self._exec_terminal(
            f"{runner} '{code_path}'",
            timeout_s=timeout_s,
            invocation_id=str(kwargs.get("invocation_id", "") or ""),
        )

    # ── Sandbox protocol: sessions ──────────────────────────────────

    async def create_session(
        self,
        config: SessionConfig | None = None,
    ) -> SessionInfo | None:
        """Lightweight: no-op command triggers container creation."""
        result = await self._exec_terminal(":", timeout_s=30)
        if result.success:
            return SessionInfo(session_id="terminal-session", container_id="")
        return None

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        """Execute code within an existing session."""
        lang_key = language.lower() if language else "python"
        ext = _LANG_EXTENSION.get(lang_key, _DEFAULT_EXTENSION)
        runner = _LANG_RUNNER.get(lang_key, _DEFAULT_RUNNER)

        code_path = f"/tmp/lca-code-{new_id('code')}.{ext}"  # noqa: S108
        await self._write_text_file(code, code_path, session_id=session_id, timeout_s=timeout_s)
        return await self._exec_terminal(
            f"{runner} '{code_path}'",
            session_id=session_id,
            timeout_s=timeout_s,
            invocation_id=str(kwargs.get("invocation_id", "") or ""),
        )

    async def destroy_session(self, session_id: str) -> None:
        """DELETE /api/v1/sessions/{id}. Idempotent."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        try:
            await client.delete(
                f"{self._base_url}/api/v1/sessions/{session_id}",
                headers=auth_headers(self._access_token),
            )
        except httpx.HTTPError:
            _log.debug("session_destroy_error", session_id=session_id, exc_info=True)
        finally:
            if owns_client:
                await client.aclose()

    # ── Extended: run_terminal (backward compat for computer runtime) ─

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        """Native shell via terminalExec channel — session-aware."""
        invocation_id = str(kwargs.get("invocation_id", "") or "")
        session_id = str(kwargs.get("session_id", "") or "")
        return await self._exec_terminal(
            command,
            session_id=session_id,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
        )
