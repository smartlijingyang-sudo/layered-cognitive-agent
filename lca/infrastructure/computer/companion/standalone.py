"""Standalone LCA Companion Runner — User Machine Side-Effect Plane (ADR-0246 M3 / CONV-INSTALL).

Zero-dependency (only standard library + httpx + websockets) standalone daemon for user local machines.
Can be downloaded directly via GET /api/device/download/companion.py and executed
with standard Python 3.10+ on Windows, macOS, and Linux without cloning the LCA repository.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import platform as sys_platform
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import httpx
except ImportError:
    print("[!] Missing dependency: httpx. Please run: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("[!] Missing dependency: websockets. Please run: pip install websockets", file=sys.stderr)
    sys.exit(1)

# Logger with fallback to standard library logging
try:
    import structlog

    _log = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    class _LogWrapper:
        def info(self, msg: str, **kwargs: Any) -> None:
            logging.info(f"{msg} {kwargs}" if kwargs else msg)

        def warning(self, msg: str, **kwargs: Any) -> None:
            logging.warning(f"{msg} {kwargs}" if kwargs else msg)

        def error(self, msg: str, **kwargs: Any) -> None:
            logging.error(f"{msg} {kwargs}" if kwargs else msg)

        def debug(self, msg: str, **kwargs: Any) -> None:
            logging.debug(f"{msg} {kwargs}" if kwargs else msg)

    _log = _LogWrapper()  # type: ignore[assignment]


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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lca-companion",
        description="LCA Local Companion Daemon for User-Machine Execution",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: pair
    p_pair = subparsers.add_parser("pair", help="Pair this machine with LCA Gateway")
    p_pair.add_argument("--server", default="http://10.36.6.252:8765", help="Gateway URL")
    p_pair.add_argument("--device-id", default=None, help="Explicit device ID")
    p_pair.add_argument("--label", default=None, help="Device label")
    p_pair.add_argument("--token-file", default=None, help="Custom token file path")
    p_pair.add_argument("--preauth-code", default=None, help="Pre-authorized code for auto-pairing")

    # Subcommand: start / run
    for cmd_name in ("start", "run"):
        p_start = subparsers.add_parser(cmd_name, help="Start the companion daemon")
        p_start.add_argument("--server", default="http://10.36.6.252:8765", help="Gateway URL")
        p_start.add_argument("--token", default=None, help="Machine token override")
        p_start.add_argument("--device-id", default=None, help="Explicit device ID")
        p_start.add_argument("--label", default=None, help="Device label")
        p_start.add_argument("--token-file", default=None, help="Custom token file path")
        p_start.add_argument(
            "--preauth-code", default=None, help="Pre-authorized code for auto-pairing"
        )
        p_start.add_argument(
            "--allow-path",
            action="append",
            dest="allowed_paths",
            default=[],
            help="Permitted directory path",
        )
        p_start.add_argument(
            "--no-commands",
            action="store_false",
            dest="allow_commands",
            help="Disable command execution",
        )

    # Subcommand: status
    p_status = subparsers.add_parser("status", help="Show companion pairing status")
    p_status.add_argument("--token-file", default=None, help="Custom token file path")

    args = parser.parse_args()

    token_file = Path(args.token_file) if getattr(args, "token_file", None) else None

    if args.subcommand == "status":
        cfg = CompanionConfig(
            token_file=token_file or Path.home() / ".lca" / "companion_token.json"
        )
        token = cfg.load_token()
        print(f"Token file: {cfg.token_file}")
        if token:
            print("Paired: Yes")
            print(f"Device ID: {cfg.device_id}")
            print(f"Label: {cfg.label}")
            print(f"Token: {token[:8]}...{token[-6:]}")
        else:
            print("Paired: No")

    elif args.subcommand == "pair":
        cfg = CompanionConfig(
            server_url=args.server,
            token_file=token_file or Path.home() / ".lca" / "companion_token.json",
        )
        if args.device_id:
            cfg.device_id = args.device_id
        if args.label:
            cfg.label = args.label
        client = CompanionClient(cfg)
        try:
            if args.preauth_code:
                asyncio.run(client.auto_pair(args.preauth_code))
            else:
                asyncio.run(client.pair())
        except KeyboardInterrupt:
            print("\nPairing aborted by user.")
            sys.exit(130)
        except Exception as exc:
            print(f"\n[!] Pairing failed: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.subcommand in ("start", "run"):
        cfg = CompanionConfig(
            server_url=args.server,
            token_file=token_file or Path.home() / ".lca" / "companion_token.json",
            allowed_paths=tuple(args.allowed_paths),
            allow_commands=args.allow_commands,
        )
        if args.token:
            cfg.machine_token = args.token
        if args.device_id:
            cfg.device_id = args.device_id
        if args.label:
            cfg.label = args.label
        client = CompanionClient(cfg)

        if not client.config.machine_token and getattr(args, "preauth_code", None):
            try:
                print(f"[*] Auto-pairing with pre-authorized code: {args.preauth_code}...")
                token = asyncio.run(client.auto_pair(args.preauth_code))
                client.config.machine_token = token
            except Exception as exc:
                print(f"\n[!] Auto-pairing failed: {exc}", file=sys.stderr)
                sys.exit(1)

        if not client.config.machine_token:
            print(
                "[!] No machine token found. Please run 'lca-companion pair' first.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"[*] Starting LCA Companion (device: {client.config.device_id}, label: {client.config.label})"
        )
        print(f"[*] Connecting to {client.config.server_url}...")
        try:
            asyncio.run(client.connect_and_run())
        except KeyboardInterrupt:
            print("\nCompanion stopped.")
            sys.exit(0)
        except Exception as exc:
            print(f"\n[!] Companion error: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
