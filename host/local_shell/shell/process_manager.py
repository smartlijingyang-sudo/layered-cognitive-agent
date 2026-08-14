"""Port of packages/local-file-shell/src/shell/process-manager.ts (POSIX)."""

from __future__ import annotations

import contextlib
import os
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen
from typing import Any


@dataclass
class _Proc:
    process: Popen[bytes]
    stdout_path: Path
    stderr_path: Path
    started_at: float
    ended_at: float | None = None
    exit_code: int | None = None
    spawn_error: str = ""


class ShellProcessManager:
    def __init__(self, output_root: str | None = None) -> None:
        self._next = 1
        now = time.localtime()
        root = Path(output_root) if output_root else Path(tempfile.gettempdir()) / "lca" / "shell"
        self._dir = root / f"{now.tm_year}-{now.tm_mon}-{now.tm_mday}" / str(os.getpid())
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)
        self._procs: dict[str, _Proc] = {}

    def create_shell_id(self) -> str:
        sid = f"sh-{self._next}"
        self._next += 1
        return sid

    def register(self, shell_id: str, proc: _Proc) -> None:
        self._procs[shell_id] = proc

    def get_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        shell_id = str(payload.get("shell_id") or payload.get("command_id") or "")
        item = self._procs.get(shell_id)
        if item is None:
            return {
                "success": False,
                "error": f"Shell ID {shell_id} not found",
                "stdout": "",
                "stderr": "",
                "output": "",
            }
        code = item.process.poll()
        timeout_ms = payload.get("timeout")
        if code is None and isinstance(timeout_ms, (int, float)) and timeout_ms > 0:
            with contextlib.suppress(TimeoutError, ProcessLookupError):
                item.process.wait(timeout=min(timeout_ms, 120_000) / 1000.0)
            code = item.process.poll()
        if code is not None:
            item.exit_code = code
            item.ended_at = time.time()
        stdout = _read_preview(item.stdout_path)
        stderr = _read_preview(item.stderr_path)
        filt = payload.get("filter")
        if filt:
            try:
                import re

                rx = re.compile(str(filt), re.M)
                stdout = "\n".join(line for line in stdout.splitlines() if rx.search(line))
                stderr = "\n".join(line for line in stderr.splitlines() if rx.search(line))
            except re.error:
                pass
        started = item.started_at
        duration = int(max(0.0, (item.ended_at or time.time()) - started) * 1000)
        return {
            "success": not item.spawn_error,
            "stdout": stdout,
            "stderr": stderr,
            "output": stdout + stderr,
            "exit_code": item.exit_code,
            "error": item.spawn_error,
            "duration_ms": duration,
            "shell_id": shell_id,
        }

    def kill(self, payload: dict[str, Any]) -> dict[str, Any]:
        shell_id = str(payload.get("shell_id") or payload.get("command_id") or "")
        item = self._procs.get(shell_id)
        if item is None:
            return {"success": False, "error": f"Shell ID {shell_id} not found"}
        pid = item.process.pid
        if pid:
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                item.process.kill()
        return {"success": True}

    def cleanup_all(self) -> None:
        for item in list(self._procs.values()):
            try:
                if item.process.poll() is None:
                    item.process.kill()
            except OSError:
                pass
        self._procs.clear()


def _read_preview(path: Path, limit: int = 18 * 1024) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    text = data[:limit].decode("utf-8", errors="replace")
    if len(data) > limit:
        return text + f"\n[truncated {len(data) - limit} bytes]"
    return text
