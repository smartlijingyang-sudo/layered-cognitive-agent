"""Run Sandbox ops on the real machine. Isolated from PTY."""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from host.local_shell.dispatch import FILE_OPS, dispatch_local
from host.paths import resolve_guest_path, rewrite_guest_refs
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT

_LANG_EXT = {"python": "py", "javascript": "js", "typescript": "ts"}
_LANG_RUNNER = {
    "python": ["python3"],
    "javascript": ["node"],
    "typescript": ["npx", "--yes", "tsx"],
}


async def handle_exec(
    op: str,
    payload: dict[str, Any],
    workspace: Path,
    *,
    mount: str = SANDBOX_MOUNT_ROOT,
) -> dict[str, Any]:
    await asyncio.to_thread(_ensure_workspace, workspace)
    if op in FILE_OPS:
        return await asyncio.to_thread(dispatch_local, op, payload, workspace, mount=mount)
    if op == "write_files":
        return await _write_files(payload, workspace, mount=mount)
    if op == "run":
        return await asyncio.to_thread(_run_code, payload, workspace, mount)
    if op == "run_terminal":
        return await asyncio.to_thread(_run_terminal, payload, workspace, mount)
    if op == "create_session":
        return {"success": True, "exit_code": 0, "session_id": uuid4().hex[:12]}
    if op == "destroy_session":
        return {"success": True, "exit_code": 0}
    return {"success": False, "exit_code": 1, "error": f"unknown op {op}"}


def _ensure_workspace(workspace: Path) -> None:
    (workspace / "outputs").mkdir(parents=True, exist_ok=True)


async def _write_files(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    base_dir = str(payload.get("base_dir") or mount)
    files = payload.get("files") or {}
    if not isinstance(files, dict):
        return {"success": False, "exit_code": 1, "error": "files must be an object"}
    for name, spec in files.items():
        dest = resolve_guest_path(f"{base_dir.rstrip('/')}/{name}", workspace, mount=mount)
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


def _run_code(payload: dict[str, Any], workspace: Path, mount: str) -> dict[str, Any]:
    language = str(payload.get("language") or "python").lower()
    code = rewrite_guest_refs(str(payload.get("code") or ""), workspace, mount=mount)
    timeout_s = int(payload.get("timeout_s") or 60)
    ext = _LANG_EXT.get(language, "py")
    runner = _LANG_RUNNER.get(language, ["python3"])
    script = workspace / ".lca-run" / f"{uuid4().hex[:8]}.{ext}"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(code, encoding="utf-8")
    return _run_argv([*runner, str(script)], workspace, timeout_s)


def _run_terminal(payload: dict[str, Any], workspace: Path, mount: str) -> dict[str, Any]:
    command = rewrite_guest_refs(str(payload.get("command") or ""), workspace, mount=mount)
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
        env = os.environ.copy()
        env["HOME"] = str(workspace)
        env["LCA_WORKSPACE"] = str(workspace)
        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_s),
            shell=shell,
            check=False,
            env=env,
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
