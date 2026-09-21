"""Stdio MCP Transport implementation with environment scrubbing."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from typing import Any

import structlog

from lca.contracts.models.mcp.types import MCPServerConfig
from lca.contracts.protocols.mcp.ports import MCPTransportPort

_log = structlog.get_logger(__name__)

# Sensitive variable regex for environment scrubbing (inspired by DeepSeek Harness)
_SENSITIVE_ENV_PATTERN = re.compile(
    r"(KEY|PASSWORD|SECRET|TOKEN|AUTH|CREDENTIAL|PRIVATE)", re.IGNORECASE
)


def scrub_parent_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Scrub parent process environment of ambient secrets, then apply explicit overrides.

    Guarantees child MCP processes only receive safe ambient variables + explicit configuration.
    """
    clean_env: dict[str, str] = {}
    for k, v in os.environ.items():
        if _SENSITIVE_ENV_PATTERN.search(k):
            continue
        clean_env[k] = v

    if extra_env:
        clean_env.update(extra_env)

    return clean_env


class StdioMCPTransport(MCPTransportPort):
    """MCP Stdio Transport via asynchronous subprocess pipes."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._proc: asyncio.subprocess.Process | None = None
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_connected(self) -> bool:
        if self._proc is None or self._proc.returncode is not None:
            return False
        try:
            curr_loop = asyncio.get_running_loop()
            if self._loop is not None and self._loop is not curr_loop:
                return False
        except RuntimeError:
            pass
        return True

    async def connect(self) -> None:
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._proc is not None and curr_loop is not None and self._loop is not curr_loop:
            self.close_sync()

        if self.is_connected:
            return

        command = self._config.command
        if not command:
            raise ValueError(f"Stdio server '{self._config.name}' must specify 'command'")

        cmd_args = [command, *self._config.args]
        env = scrub_parent_env(self._config.env)

        _log.info(
            "mcp_stdio_spawning",
            server=self._config.name,
            command=command,
            args=self._config.args,
        )

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._config.cwd,
            )
            self._loop = curr_loop
            self._lock = asyncio.Lock()
        except Exception as e:
            _log.error("mcp_stdio_spawn_failed", server=self._config.name, error=str(e))
            raise RuntimeError(f"Failed to spawn MCP server '{self._config.name}': {e}") from e

    async def send_message(self, message: dict[str, Any]) -> None:
        if not self.is_connected or self._proc is None or self._proc.stdin is None:
            await self.connect()
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError(f"MCP server '{self._config.name}' stdin is not available")

        if self._lock is None:
            self._lock = asyncio.Lock()

        payload = json.dumps(message, ensure_ascii=False) + "\n"
        async with self._lock:
            self._proc.stdin.write(payload.encode("utf-8"))
            await self._proc.stdin.drain()

    async def receive_message(self, timeout_s: float | None = None) -> dict[str, Any]:
        if not self.is_connected or self._proc is None or self._proc.stdout is None:
            raise RuntimeError(f"MCP server '{self._config.name}' stdio is not connected")

        async def _read_line() -> str:
            if self._proc is None or self._proc.stdout is None:
                raise RuntimeError(f"MCP server '{self._config.name}' stdout is not available")
            while True:
                line_bytes = await self._proc.stdout.readline()
                if not line_bytes:
                    stderr_msg = ""
                    if self._proc.stderr:
                        stderr_bytes = await self._proc.stderr.read()
                        stderr_msg = stderr_bytes.decode("utf-8", errors="replace")
                    raise EOFError(
                        f"MCP server '{self._config.name}' closed stdout. Stderr: {stderr_msg[:500]}"
                    )
                line = line_bytes.decode("utf-8").strip()
                if line:
                    return line

        try:
            if timeout_s is not None:
                line = await asyncio.wait_for(_read_line(), timeout=timeout_s)
            else:
                line = await _read_line()
            return json.loads(line)  # type: ignore[no-any-return]
        except TimeoutError as exc:
            raise TimeoutError(f"MCP server '{self._config.name}' timed out waiting for response") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from MCP server '{self._config.name}': {exc}") from exc

    async def close(self) -> None:
        if self._proc is not None:
            proc = self._proc
            self._proc = None
            self._lock = None
            self._loop = None
            with contextlib.suppress(Exception):
                if proc.stdin is not None:
                    with contextlib.suppress(Exception):
                        proc.stdin.close()

                if proc.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1.5)
                    except (TimeoutError, Exception):
                        with contextlib.suppress(ProcessLookupError):
                            proc.kill()
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(proc.wait(), timeout=1.5)

                transport = getattr(proc, "_transport", None)
                if transport is not None:
                    transport._closed = True
                    for pipe_name in ("_stdin", "_stdout", "_stderr"):
                        pipe_proto = getattr(transport, pipe_name, None)
                        if pipe_proto is not None and hasattr(pipe_proto, "pipe") and pipe_proto.pipe is not None:
                            with contextlib.suppress(Exception):
                                pipe_proto.pipe.close()
                    with contextlib.suppress(Exception):
                        transport.close()
            with contextlib.suppress(Exception):
                await asyncio.sleep(0)

    def close_sync(self) -> None:
        """Synchronously terminate child process and release pipes without active loop."""
        if self._proc is not None:
            proc = self._proc
            self._proc = None
            self._lock = None
            self._loop = None
            with contextlib.suppress(Exception):
                if proc.stdin is not None:
                    with contextlib.suppress(Exception):
                        proc.stdin.close()
                if proc.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        proc.terminate()
                    with contextlib.suppress(Exception):
                        proc.kill()
                with contextlib.suppress(Exception):
                    if proc.pid is not None:
                        for _ in range(10):
                            pid_res, _ = os.waitpid(proc.pid, os.WNOHANG)
                            if pid_res != 0:
                                break
                            time.sleep(0.01)
                transport = getattr(proc, "_transport", None)
                if transport is not None:
                    transport._closed = True
                    for pipe_name in ("_stdin", "_stdout", "_stderr"):
                        pipe_proto = getattr(transport, pipe_name, None)
                        if pipe_proto is not None and hasattr(pipe_proto, "pipe") and pipe_proto.pipe is not None:
                            with contextlib.suppress(Exception):
                                pipe_proto.pipe.close()
