"""Local Companion Client — User Machine Side-Effect Plane (ADR-0246 M3).

Connects local machine to LCA Gateway via WebSocket and executes
permitted operations (command, file read/write) with local capability checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import os
import platform as sys_platform
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import structlog
import websockets

_log = structlog.get_logger(__name__)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as exc:
        return getattr(exc, "errno", None) == errno.EPERM
    except Exception:
        return False


@dataclass
class CompanionConfig:
    server_url: str = "http://10.36.6.252:8765"
    device_id: str = field(default_factory=lambda: f"m-{socket.gethostname().lower()}")
    label: str = field(default_factory=socket.gethostname)
    platform: str = field(default_factory=sys_platform.system)
    machine_token: str | None = None
    allowed_paths: tuple[str, ...] = ()
    allow_commands: bool = True
    token_file: Path | None = field(
        default_factory=lambda: Path.home() / ".lca" / "companion_token.json"
    )
    state_file: Path | None = field(
        default_factory=lambda: Path.home() / ".lca" / "companion_state.json"
    )

    def save_token(
        self, token: str, user_id: str | None = None, workspace_id: str | None = None
    ) -> None:
        self.machine_token = token
        if not self.token_file:
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "device_id": self.device_id,
            "label": self.label,
            "machine_token": token,
            "user_id": user_id,
            "workspace_id": workspace_id,
        }
        self.token_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_token(self) -> str | None:
        if not self.token_file or not self.token_file.exists():
            return None
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
            token = data.get("machine_token")
            if token:
                self.machine_token = str(token)
                if data.get("device_id"):
                    self.device_id = str(data["device_id"])
                if data.get("label"):
                    self.label = str(data["label"])
                return self.machine_token
        except Exception as exc:
            _log.warning("failed_to_load_companion_token", error=str(exc))
        return None


class CompanionClient:
    """Daemon running on user's machine to execute side-effects via GatewayClient protocol."""

    def __init__(self, config: CompanionConfig | None = None) -> None:
        self.config = config or CompanionConfig()
        if not self.config.machine_token:
            self.config.load_token()

    def write_state(
        self,
        state_file: Path | None = None,
        pid: int | None = None,
        status: str = "running",
    ) -> None:
        target = state_file or self.config.state_file
        if not target:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": pid if pid is not None else os.getpid(),
            "device_id": self.config.device_id,
            "label": self.config.label,
            "server_url": self.config.server_url,
            "status": status,
            "started_at": datetime.now(UTC).isoformat(),
        }
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_state(self, state_file: Path | None = None) -> None:
        target = state_file or self.config.state_file
        if target and target.exists():
            with contextlib.suppress(OSError):
                target.unlink()

    def is_another_instance_running(self, state_file: Path | None = None) -> bool:
        target = state_file or self.config.state_file
        if not target or not target.exists():
            return False
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid and isinstance(pid, int):
                if pid == os.getpid():
                    return False
                return is_process_alive(pid)
        except Exception:
            return False
        return False

    def _check_path(self, path: str) -> str:
        norm = os.path.abspath(os.path.expanduser(path))
        if self.config.allowed_paths:
            allowed = False
            for p in self.config.allowed_paths:
                norm_p = os.path.abspath(os.path.expanduser(p))
                if norm == norm_p or norm.startswith(norm_p + os.sep):
                    allowed = True
                    break
            if not allowed:
                raise PermissionError(f"Access denied: path '{path}' is outside permitted scopes")
        return norm

    async def request_pairing(self, user_code: str | None = None) -> dict[str, Any]:
        url = f"{self.config.server_url.rstrip('/')}/api/device/pair/code"
        payload = {
            "deviceId": self.config.device_id,
            "label": self.config.label,
            "platform": self.config.platform,
        }
        if user_code:
            payload["userCode"] = user_code
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def auto_pair(self, preauth_code: str) -> str:
        req = await self.request_pairing(user_code=preauth_code)
        token = req.get("machineToken")
        if token:
            user_id = req.get("userId")
            workspace_id = req.get("workspaceId")
            self.config.save_token(token, user_id=user_id, workspace_id=workspace_id)
            print(f"[✓] Auto-pairing successful! Token saved to {self.config.token_file}")
            return token

        device_code = req.get("deviceCode")
        if not device_code:
            raise RuntimeError(f"Unexpected response from pairing endpoint: {req}")

        res = await self.poll_pairing(device_code)
        if res.get("status") == "success" and res.get("machineToken"):
            token = res["machineToken"]
            user_id = res.get("userId")
            workspace_id = res.get("workspaceId")
            self.config.save_token(token, user_id=user_id, workspace_id=workspace_id)
            print(f"[✓] Auto-pairing successful! Token saved to {self.config.token_file}")
            return token

        raise RuntimeError(f"Auto-pairing failed with response: {req}")

    async def poll_pairing(self, device_code: str) -> dict[str, Any]:
        url = f"{self.config.server_url.rstrip('/')}/api/device/pair/poll"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"deviceCode": device_code}, timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def pair(self, timeout_s: float = 300.0, interval: float = 2.0) -> str:
        req = await self.request_pairing()
        device_code = req["deviceCode"]
        user_code = req["userCode"]
        verification_uri = req.get("verificationUri", "/pair")
        poll_interval = float(req.get("interval") or interval)

        print("\n" + "=" * 60)
        print("  Pairing Companion to LCA Gateway")
        print(f"  Please enter the code in your browser UI:  {user_code}")
        print(f"  Verification URI: {verification_uri}")
        print("=" * 60 + "\n")

        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < timeout_s:
            await asyncio.sleep(poll_interval)
            res = await self.poll_pairing(device_code)
            status = res.get("status")
            if status == "success":
                token = res["machineToken"]
                user_id = res.get("userId")
                workspace_id = res.get("workspaceId")
                self.config.save_token(token, user_id=user_id, workspace_id=workspace_id)
                print(f"[✓] Pairing successful! Token saved to {self.config.token_file}")
                return token
            if status == "expired":
                raise TimeoutError("Pairing code expired before authorization")
            if status != "authorization_pending":
                raise RuntimeError(f"Pairing failed with status: {status}")

        raise TimeoutError("Pairing timed out waiting for user confirmation")

    async def dispatch_tool(self, api_name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except Exception:
                args = {}
        else:
            args = arguments or {}

        try:
            if api_name == "runCommand":
                return await self._run_command(args)
            if api_name == "readFile":
                return await self._read_file(args)
            if api_name == "writeFile":
                return await self._write_file(args)
            if api_name == "listFiles":
                return await self._list_files(args)
            if api_name == "editFile":
                return await self._edit_file(args)
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": f"Unknown apiName: {api_name}",
                "exit_code": 1,
                "error": f"Unknown apiName: {api_name}",
            }
        except Exception as exc:
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": str(exc),
                "exit_code": 1,
                "error": str(exc),
            }

    async def _run_command(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.config.allow_commands:
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": "Commands execution is disabled on this companion",
                "exit_code": 1,
                "error": "commands_disabled",
            }
        command = str(args.get("command") or "")
        raw_cwd = args.get("cwd")
        cwd = self._check_path(str(raw_cwd)) if raw_cwd else os.getcwd()
        timeout = float(args.get("timeout_s") or args.get("timeout") or 60.0)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else 0
            return {
                "success": exit_code == 0,
                "content": stdout,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "error": stderr if exit_code != 0 else "",
            }
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": 124,
                "error": "command_timeout",
            }

    async def _read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._check_path(str(args.get("path") or ""))
        return await asyncio.to_thread(
            self._sync_read_file, path, args.get("start_line"), args.get("end_line")
        )

    def _sync_read_file(
        self, path: str, start_line: int | None, end_line: int | None
    ) -> dict[str, Any]:
        if not os.path.exists(path):
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": f"File not found: {path}",
                "exit_code": 1,
                "error": "file_not_found",
            }
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        if start_line is not None or end_line is not None:
            lines = text.splitlines(keepends=True)
            s = max(0, int(start_line) - 1) if start_line is not None else 0
            e = int(end_line) if end_line is not None else len(lines)
            text = "".join(lines[s:e])
        return {
            "success": True,
            "content": text,
            "stdout": text,
            "stderr": "",
            "exit_code": 0,
            "error": "",
        }

    async def _write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._check_path(str(args.get("path") or ""))
        content = str(args.get("content") or "")
        create_dirs = bool(args.get("create_directories", True))
        return await asyncio.to_thread(self._sync_write_file, path, content, create_dirs)

    def _sync_write_file(self, path: str, content: str, create_directories: bool) -> dict[str, Any]:
        if create_directories:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        msg = f"Successfully wrote {len(content)} characters to {path}"
        return {
            "success": True,
            "content": msg,
            "stdout": msg,
            "stderr": "",
            "exit_code": 0,
            "error": "",
        }

    async def _list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._check_path(str(args.get("directory_path") or args.get("directory") or "."))
        return await asyncio.to_thread(self._sync_list_files, path)

    def _sync_list_files(self, path: str) -> dict[str, Any]:
        if not os.path.isdir(path):
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": f"Directory not found: {path}",
                "exit_code": 1,
                "error": "dir_not_found",
            }
        items = os.listdir(path)
        content = "\n".join(items)
        return {
            "success": True,
            "content": content,
            "stdout": content,
            "stderr": "",
            "exit_code": 0,
            "error": "",
            "files": items,
        }

    async def _edit_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._check_path(str(args.get("path") or ""))
        search = str(args.get("search") or "")
        replace = str(args.get("replace") or "")
        replace_all = bool(args.get("replace_all", False))
        return await asyncio.to_thread(self._sync_edit_file, path, search, replace, replace_all)

    def _sync_edit_file(
        self, path: str, search: str, replace: str, replace_all: bool
    ) -> dict[str, Any]:
        if not os.path.exists(path):
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": f"File not found: {path}",
                "exit_code": 1,
                "error": "file_not_found",
            }
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        if search not in text:
            return {
                "success": False,
                "content": "",
                "stdout": "",
                "stderr": "Search target string not found",
                "exit_code": 1,
                "error": "target_not_found",
            }
        count = -1 if replace_all else 1
        new_text = text.replace(search, replace, count)
        Path(path).write_text(new_text, encoding="utf-8")
        return {
            "success": True,
            "content": "File modified successfully",
            "stdout": "File modified successfully",
            "stderr": "",
            "exit_code": 0,
            "error": "",
        }

    def dispatch_rpc(self, method: str, params: Any) -> Any:
        del params
        if method == "systemInfo":
            return {
                "device_id": self.config.device_id,
                "label": self.config.label,
                "platform": self.config.platform,
                "hostname": socket.gethostname(),
                "python": sys_platform.python_version(),
            }
        return {"error": f"Unknown RPC method: {method}"}

    async def connect_and_run(self, stop_event: asyncio.Event | None = None) -> None:
        if not self.config.machine_token:
            raise ValueError("machine_token is required to connect. Run pairing first.")

        server = self.config.server_url.rstrip("/")
        if server.startswith("https://"):
            ws_proto = "wss"
            server_host = server[8:]
        elif server.startswith("http://"):
            ws_proto = "ws"
            server_host = server[7:]
        else:
            ws_proto = "ws"
            server_host = server

        connection_id = uuid4().hex[:16]
        ws_url = (
            f"{ws_proto}://{server_host}/api/device/ws?"
            f"deviceId={self.config.device_id}&connectionId={connection_id}&"
            f"hostname={socket.gethostname()}&platform={self.config.platform}&channel=companion"
        )

        user_home = os.path.expanduser("~")  # noqa: ASYNC240
        current_workdir = os.getcwd()

        _log.info("connecting_to_gateway", url=ws_url)
        async with websockets.connect(ws_url) as ws:
            # 1. Auth handshake
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "token": self.config.machine_token,
                        "tokenType": "machineToken",
                        "home": user_home,
                        "workspace": current_workdir,
                    }
                )
            )
            raw_auth = await ws.recv()
            auth_ack = json.loads(raw_auth)
            if auth_ack.get("type") != "auth_success":
                raise PermissionError(f"Gateway auth rejected: {auth_ack.get('reason')}")

            _log.info("companion_online", device_id=self.config.device_id)

            while stop_event is None or not stop_event.is_set():
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    break

                try:
                    msg = json.loads(raw_msg)
                except Exception as exc:
                    _log.debug("invalid_json_received", error=str(exc))
                    continue

                msg_type = msg.get("type")
                if msg_type == "heartbeat":
                    await ws.send(json.dumps({"type": "heartbeat_ack"}))
                elif msg_type == "tool_call_request":
                    req_id = msg.get("requestId", "")
                    tool_call = msg.get("toolCall", {})
                    api_name = tool_call.get("apiName", "")
                    arguments = tool_call.get("arguments", {})
                    result = await self.dispatch_tool(api_name, arguments)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "tool_call_response",
                                "requestId": req_id,
                                "result": result,
                            }
                        )
                    )
                elif msg_type == "rpc_request":
                    req_id = msg.get("requestId", "")
                    method = msg.get("method", "")
                    params = msg.get("params")
                    result = self.dispatch_rpc(method, params)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "rpc_response",
                                "requestId": req_id,
                                "result": result,
                            }
                        )
                    )
