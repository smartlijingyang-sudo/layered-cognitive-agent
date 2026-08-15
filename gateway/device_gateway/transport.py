"""MachineTransport that relays through DeviceHub (LobeHub tool_call protocol)."""

from __future__ import annotations

import base64
from typing import Any

from gateway.device_gateway.hub import DeviceHub, encode_arguments
from gateway.device_gateway.registry import DeviceRegistry
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.layer0_infra.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _COMPUTER_IDENTIFIER


class DeviceTransport:
    """Bound computer: one online device, spoken to via tool_call_request."""

    name = "device"

    def __init__(self, registry: DeviceRegistry, hub: DeviceHub, device_id: str) -> None:
        self._registry = registry
        self._hub = hub
        self._device_id = device_id

    @classmethod
    def for_device(
        cls, registry: DeviceRegistry, hub: DeviceHub, device_id: str
    ) -> DeviceTransport | None:
        device = registry.get(device_id)
        if device is None or not device.online:
            return None
        return cls(registry, hub, device.device_id)

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        del session_id
        encoded: dict[str, dict[str, str]] = {}
        for name, source in files.items():
            if isinstance(source, bytes):
                encoded[name] = {"b64": base64.b64encode(source).decode("ascii")}
            else:
                encoded[name] = {"url": source}
        # system=true: MachineTransport.write_files 是系统通道（附件暂存），
        # 等价于 Sandbox.write_files()。CLI 跳过 assertWritable。
        # 用户写入走 computer_op("writeFile", ...) — 不同的 CLI tool，有策略。
        return await self._invoke(
            "writeFiles",
            {"files": encoded, "base_dir": base_dir, "system": True},
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
            "executeCode",
            {"code": code, "language": language, "timeout_s": timeout_s},
            timeout_s=timeout_s,
        )

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        del config
        return None

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        del session_id, kwargs
        return await self.run(code, language=language, timeout_s=timeout_s)

    async def destroy_session(self, session_id: str) -> None:
        del session_id

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        del kwargs
        return await self._invoke("runCommand", {"command": command}, timeout_s=timeout_s)

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        try:
            return await self._raw(op, args, timeout_s=timeout_s + 5)
        except TimeoutError as exc:
            return {"success": False, "error": str(exc), "retryable": True}

    async def _invoke(
        self, api_name: str, payload: dict[str, Any], *, timeout_s: int
    ) -> SandboxResult:
        try:
            body = await self._raw(api_name, payload, timeout_s=timeout_s + 5)
        except TimeoutError:
            return SandboxResult(
                success=False, exit_code=1, error=f"device {api_name} timed out", stderr="timeout\n"
            )
        except ConnectionError as exc:
            return SandboxResult(success=False, exit_code=1, error=str(exc), stderr=str(exc) + "\n")
        return SandboxResult(
            stdout=str(body.get("content") or body.get("stdout") or ""),
            stderr=str(body.get("stderr") or ""),
            exit_code=int(body.get("exit_code") or 0),
            success=bool(body.get("success", False)),
            error=str(body.get("error") or ""),
        )

    async def _raw(
        self, api_name: str, payload: dict[str, Any], *, timeout_s: float
    ) -> dict[str, Any]:
        return await self._hub.call_tool(
            self._device_id,
            {
                "identifier": _COMPUTER_IDENTIFIER,
                "apiName": api_name,
                "arguments": encode_arguments(payload),
                "type": "tool",
            },
            timeout_s=timeout_s,
        )
