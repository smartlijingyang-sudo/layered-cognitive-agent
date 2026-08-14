# ruff: noqa: S603, S607
"""Process primitives: pid files, kill trees, ports, public URL."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path


def read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text.isdigit():
        return None
    return int(text)


def write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def start_epoch(pid: int) -> float | None:
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return None
    return proc.stat().st_ctime


def listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def wait_for_port(port: int, timeout_s: float = 10.0, host: str = "127.0.0.1") -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if listening(port, host):
            return True
        time.sleep(0.25)
    return False


def children_of(pid: int) -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(line) for line in result.stdout.split() if line.isdigit()]


def kill_tree(pid: int, sig: int = signal.SIGTERM) -> None:
    if not pid_alive(pid):
        return
    for child in children_of(pid):
        kill_tree(child, sig)
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        return


def stop_pid(pid: int, *, wait_s: float = 8.0) -> None:
    kill_tree(pid, signal.SIGTERM)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and pid_alive(pid):
        time.sleep(0.2)
    if pid_alive(pid):
        kill_tree(pid, signal.SIGKILL)


def pgrep_f(pattern: str) -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(line) for line in result.stdout.split() if line.isdigit()]


def port_holder(port: int) -> int | None:
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    needle = f":{port}"
    for line in result.stdout.splitlines():
        if needle not in line or "pid=" not in line:
            continue
        after = line.split("pid=", 1)[1]
        digits = "".join(ch for ch in after if ch.isdigit())
        if digits:
            return int(digits)
    return None


def public_url(port: int) -> str:
    explicit = os.environ.get("GATEWAY_PUBLIC_URL") or os.environ.get("LCA_GATEWAY_PUBLIC_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("LOBE_LAN_IP") or os.environ.get("VITE_DEV_HOST") or ""
    if not host:
        host = _lan_ip()
    if not host or host == "0.0.0.0":  # noqa: S104
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _lan_ip() -> str:
    try:
        result = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None:
        parts = result.stdout.split()
        if "src" in parts:
            return parts[parts.index("src") + 1]
    try:
        hostname = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return hostname.stdout.split()[0] if hostname.stdout.split() else ""
