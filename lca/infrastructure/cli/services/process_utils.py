"""Process / port utilities shared by lca-ops service modules.

Used by ``KernelServeService.restart()`` / ``stop()`` to find an existing
``lca_kernel serve`` PID and to wait for a TCP port to free up.
"""

from __future__ import annotations

import socket
from pathlib import Path


def find_pid_by_argv(*needles: str) -> object | None:
    """Return the first PID whose ``/proc/<pid>/cmdline`` contains all needles.

    Returns ``None`` when nothing matches. The return value is typed as
    ``object`` (a ``psutil.Process``-like proxy from ``psutil`` if installed,
    else a minimal stand-in) so callers don't import psutil directly.
    """
    try:
        import psutil  # type: ignore[import-not-found]

        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            joined = " ".join(cmdline)
            if all(needle in joined for needle in needles):
                return proc
        return None
    except ImportError:
        # Fall back to /proc scan (Linux only); returns a minimal stand-in.
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            except (FileNotFoundError, PermissionError):
                continue
            if all(needle in cmdline for needle in needles):
                return _ProcfsProxy(int(pid_dir.name))
        return None


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """True iff ``host:port`` accepts a TCP connection right now."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class _ProcfsProxy:
    """Minimal Process-shaped stand-in used when ``psutil`` is unavailable."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def send_signal(self, sig: int) -> None:
        import contextlib
        import os
        with contextlib.suppress(ProcessLookupError):
            os.kill(self.pid, sig)


__all__ = ["find_pid_by_argv", "port_listening"]
