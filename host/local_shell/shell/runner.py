"""Port of packages/local-file-shell/src/shell/runner.ts (POSIX /bin/sh)."""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from subprocess import DEVNULL, Popen
from typing import Any

from host.local_shell.file.bind import resolve_bound
from host.local_shell.shell.process_manager import ShellProcessManager, _Proc

_MANAGER = ShellProcessManager()


def process_manager() -> ShellProcessManager:
    return _MANAGER


def run_command(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    command = str(payload.get("command") or "")
    if not command:
        return {"success": False, "error": "command is required"}
    cwd_raw = payload.get("cwd")
    cwd = resolve_bound(str(cwd_raw), workspace, mount=mount) if cwd_raw else str(workspace)
    timeout_ms = payload.get("timeout")
    if isinstance(timeout_ms, (int, float)) and timeout_ms > 0:
        wait_s = min(float(timeout_ms) / 1000.0, 120.0)
    else:
        wait_s = float(payload.get("timeout_s") or 30)
    background = bool(payload.get("run_in_background") or payload.get("background"))
    manager = _MANAGER
    shell_id = manager.create_shell_id()
    out_dir = manager._dir / shell_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    env = os.environ.copy()
    extra = payload.get("env")
    if isinstance(extra, dict):
        env.update({str(k): str(v) for k, v in extra.items()})
    env["HOME"] = str(workspace)
    env["LCA_WORKSPACE"] = str(workspace)
    try:
        stdout_f = stdout_path.open("wb")
        stderr_f = stderr_path.open("wb")
        proc = Popen(  # noqa: S603
            ["/bin/sh", "-c", command],
            cwd=cwd,
            stdin=DEVNULL,
            stdout=stdout_f,
            stderr=stderr_f,
            env=env,
            start_new_session=True,
        )
        stdout_f.close()
        stderr_f.close()
    except OSError as exc:
        return {"success": False, "error": str(exc)}
    record = _Proc(
        process=proc,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        started_at=time.time(),
    )
    manager.register(shell_id, record)
    if background:
        return {"success": True, "shell_id": shell_id, "output": "", "stdout": "", "stderr": ""}
    with contextlib.suppress(TimeoutError, ProcessLookupError):
        code = proc.wait(timeout=wait_s)
        record.exit_code = code
        record.ended_at = time.time()
    return manager.get_output({"shell_id": shell_id, "timeout": 0})
