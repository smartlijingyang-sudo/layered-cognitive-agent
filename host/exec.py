"""Run Sandbox ops on the real machine. Isolated from PTY."""

from __future__ import annotations

import asyncio
import base64
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT

_LANG_EXT = {"python": "py", "javascript": "js", "typescript": "ts"}
_LANG_RUNNER = {
    "python": ["python3"],
    "javascript": ["node"],
    "typescript": ["npx", "--yes", "tsx"],
}


def resolve_guest_path(raw: str, workspace: Path) -> Path:
    text = raw.strip() or "."
    if text == SANDBOX_MOUNT_ROOT or text.startswith(f"{SANDBOX_MOUNT_ROOT}/"):
        rest = text[len(SANDBOX_MOUNT_ROOT) :].lstrip("/")
        return (workspace / rest).resolve()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


async def handle_exec(op: str, payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    await asyncio.to_thread(workspace.mkdir, parents=True, exist_ok=True)
    if op == "write_files":
        return await _write_files(payload, workspace)
    if op == "run":
        return await asyncio.to_thread(_run_code, payload, workspace)
    if op == "run_terminal":
        return await asyncio.to_thread(_run_terminal, payload, workspace)
    if op == "create_session":
        return {"success": True, "exit_code": 0, "session_id": uuid4().hex[:12]}
    if op == "destroy_session":
        return {"success": True, "exit_code": 0}
    return {"success": False, "exit_code": 1, "error": f"unknown op {op}"}


async def _write_files(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    base_dir = str(payload.get("base_dir") or SANDBOX_MOUNT_ROOT)
    files = payload.get("files") or {}
    if not isinstance(files, dict):
        return {"success": False, "exit_code": 1, "error": "files must be an object"}
    for name, spec in files.items():
        dest = resolve_guest_path(f"{base_dir.rstrip('/')}/{name}", workspace)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await _materialize(spec))
    return {"success": True, "exit_code": 0}


async def _materialize(spec: object) -> bytes:
    if isinstance(spec, dict) and spec.get("url"):
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(str(spec["url"]))
            response.raise_for_status()
            return response.content
    if isinstance(spec, dict) and spec.get("b64"):
        return base64.b64decode(str(spec["b64"]))
    return b""


def _run_code(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    language = str(payload.get("language") or "python").lower()
    code = str(payload.get("code") or "")
    timeout_s = int(payload.get("timeout_s") or 60)
    ext = _LANG_EXT.get(language, "py")
    runner = _LANG_RUNNER.get(language, ["python3"])
    script = workspace / ".lca-run" / f"{uuid4().hex[:8]}.{ext}"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(code, encoding="utf-8")
    return _run_argv([*runner, str(script)], workspace, timeout_s)


def _run_terminal(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    command = str(payload.get("command") or "")
    timeout_s = int(payload.get("timeout_s") or 60)
    return _run_argv(command, workspace, timeout_s, shell=True)  # noqa: S604


def _run_argv(
    argv: list[str] | str,
    workspace: Path,
    timeout_s: int,
    *,
    shell: bool = False,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_s),
            shell=shell,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": 1,
            "error": "timeout",
            "stderr": "timeout\n",
            "stdout": "",
        }
    except OSError as exc:
        return {"success": False, "exit_code": 1, "error": str(exc), "stderr": str(exc) + "\n"}
    return {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "error": "" if completed.returncode == 0 else (completed.stderr or "command failed"),
    }
