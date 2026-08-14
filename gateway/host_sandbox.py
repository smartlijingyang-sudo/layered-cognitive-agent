"""Sandbox implementation that RPCs to the connected host sidecar.

Gateway-only. Tools still speak Sandbox; they never see Presence.
"""

from __future__ import annotations

import base64
from typing import Any

from gateway.presence.models import CAP_SANDBOX
from gateway.presence.registry import PresenceRegistry
from gateway.presence.rpc import ExecHub
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)


class HostSandbox:
    """Bound computer: one online host with the sandbox capability."""

    name = "host"

    def __init__(self, presence: PresenceRegistry, hub: ExecHub, device_id: str) -> None:
        self._presence = presence
        self._hub = hub
        self._device_id = device_id

    @classmethod
    def for_device(
        cls, presence: PresenceRegistry, hub: ExecHub, device_id: str
    ) -> HostSandbox | None:
        device = presence.get(device_id)
        if device is None or presence.channel(device_id) is None:
            return None
        if CAP_SANDBOX not in device.capabilities:
            return None
        return cls(presence, hub, device.device_id)

    @classmethod
    def from_presence(cls, presence: PresenceRegistry, hub: ExecHub) -> HostSandbox | None:
        """Exactly one online sandbox-capable device. Never silently pick the first of N."""
        device = presence.first_online(CAP_SANDBOX)
        if device is None:
            return None
        return cls.for_device(presence, hub, device.device_id)

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        encoded: dict[str, dict[str, str]] = {}
        for name, source in files.items():
            if isinstance(source, bytes):
                encoded[name] = {"b64": base64.b64encode(source).decode("ascii")}
            else:
                encoded[name] = {"url": source}
        return await self._invoke(
            "write_files",
            {
                "files": encoded,
                "base_dir": base_dir,
                "session_id": session_id,
            },
            timeout_s=timeout_s,
        )

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self._invoke(
            "run",
            {
                "code": code,
                "language": language,
                "session_id": str(kwargs.get("session_id") or ""),
                "timeout_s": timeout_s,
            },
            timeout_s=timeout_s,
        )

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        del config
        reply = await self._raw("create_session", {}, timeout_s=30)
        result = _result_body(reply)
        session_id = str(result.get("session_id") or "")
        if not session_id:
            return None
        return SessionInfo(session_id=session_id)

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        del kwargs
        return await self._invoke(
            "run",
            {
                "code": code,
                "language": language,
                "session_id": session_id,
                "timeout_s": timeout_s,
            },
            timeout_s=timeout_s,
        )

    async def destroy_session(self, session_id: str) -> None:
        await self._raw("destroy_session", {"session_id": session_id}, timeout_s=15)

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self._invoke(
            "run_terminal",
            {
                "command": command,
                "session_id": str(kwargs.get("session_id") or ""),
                "timeout_s": timeout_s,
            },
            timeout_s=timeout_s,
        )

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        """Named local-file-shell op. ComputerRuntime uses this instead of guest Python."""
        try:
            reply = await self._raw(op, args, timeout_s=timeout_s + 5)
        except TimeoutError as exc:
            return {"success": False, "error": str(exc), "retryable": True}
        except ConnectionError:
            raise
        body = _result_body(reply)
        if "success" not in body:
            body["success"] = bool(reply.get("ok", False))
        return body

    async def _invoke(self, op: str, payload: dict[str, Any], *, timeout_s: int) -> SandboxResult:
        try:
            reply = await self._raw(op, payload, timeout_s=timeout_s + 5)
        except TimeoutError:
            return SandboxResult(
                success=False, exit_code=1, error=f"host {op} timed out", stderr="timeout\n"
            )
        except ConnectionError as exc:
            return SandboxResult(success=False, exit_code=1, error=str(exc), stderr=str(exc) + "\n")
        body = _result_body(reply)
        return SandboxResult(
            stdout=str(body.get("stdout") or ""),
            stderr=str(body.get("stderr") or ""),
            exit_code=int(body.get("exit_code") or 0),
            success=bool(body.get("success", False)),
            error=str(body.get("error") or ""),
        )

    async def _raw(self, op: str, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
        channel = self._presence.channel(self._device_id)
        if channel is None:
            raise ConnectionError(f"host {self._device_id} offline")
        return await self._hub.call(channel, op, payload, timeout_s=timeout_s)


def _result_body(reply: dict[str, Any]) -> dict[str, Any]:
    result = reply.get("result")
    return result if isinstance(result, dict) else {}
