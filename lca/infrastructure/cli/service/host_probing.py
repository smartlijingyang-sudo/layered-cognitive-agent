"""Host-probing primitives for CLI services.

Pure process/port/HTTP probing used by the service implementations'
``state()`` / ``heal()`` / ``stop()`` methods: kill a process tree,
release a port, find the PID behind a port, and HTTP readiness probes.
No process is spawned for observation other than the probe commands
themselves; every probe is best-effort and fail-safe.

Split out of ``service.py`` (RA-083): the Service Protocol surface
(``Service``/``ServiceState``) must stay importable
without the host-probing machinery.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


def resolve_probe_cmd(name: str) -> str:
    """Resolve an executable name to its absolute binary path on host."""
    path = shutil.which(name)
    if path:
        return path
    for prefix in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        candidate = f"{prefix}/{name}"
        if os.path.exists(candidate):
            return candidate
    return name


# ── Process management primitives ─────────────────────────────────────


def kill_tree(pid: int, sig: int = 15) -> None:
    """Kill a process and all its descendants."""
    if pid <= 0:
        return

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return

    # Kill children first (depth-first)
    try:
        pgrep = resolve_probe_cmd("pgrep")
        children = subprocess.run(  # noqa: S603 -- argv fixed with internal pid
            [pgrep, "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for child_pid in children.stdout.strip().split("\n"):
            if child_pid.strip():
                kill_tree(int(child_pid.strip()), sig)
    except Exception as exc:
        # INTENTIONAL: kill_tree 在 subprocess 不在时抛;视为 cleanup 已完成。
        logger.debug("kill_tree child scan ignored error: %s", exc)

    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, sig)


def free_port(port: int) -> None:
    """Release a port from any holder."""
    fuser = resolve_probe_cmd("fuser")
    with contextlib.suppress(Exception):
        subprocess.run(  # noqa: S603 -- port is typed int
            [fuser, "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5,
        )


def pid_alive(pid: int) -> bool:
    """Check if a PID is alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def pid_on_port(port: int) -> int | None:
    """Return a PID listening on ``port``, or None if none found.

    Prefer ``lsof`` / ``ss``. ``fuser`` is not used: it prints stray PIDs
    that are not bound to the port, which made the Vite sidecar look up.
    """
    lsof = resolve_probe_cmd("lsof")
    try:
        result = subprocess.run(  # noqa: S603 -- port is typed int
            [lsof, "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                return int(line.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # INTENTIONAL: port 查询命令失败 / 端口空闲 / 输出不可解析 → 回 None,
        # caller 视为"无 holder",走下一种释放策略。
        pass

    ss = resolve_probe_cmd("ss")
    try:
        result = subprocess.run(  # noqa: S603 -- constant argv
            [ss, "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        bound = re.compile(rf":{port}\s")
        for line in result.stdout.splitlines():
            if not bound.search(line):
                continue
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # INTENTIONAL: port owner 不存在 / lsof 缺失 / 解析失败 → 回 None,
        # caller 走其他路径,port release 是 best-effort。
        pass
    return None


def pid_on_listening_port(port: int) -> int | None:
    """Return the PID of the process LISTENING on ``port``, or None.

    Unlike ``pid_on_port``, this only counts listening sockets, so a browser's
    outbound connection to the dev server never looks like the port is still
    occupied. Used when waiting for a port to be released after a kill.
    """
    ss = resolve_probe_cmd("ss")
    try:
        result = subprocess.run(  # noqa: S603 -- constant argv
            [ss, "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        bound = re.compile(rf":{port}\s")
        for line in result.stdout.splitlines():
            if not bound.search(line):
                continue
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # INTENTIONAL: ss 缺失或解析失败 → 无法确认监听者,回 None。
        pass
    return None


def http_ready(url: str, timeout: float = 2.0) -> bool:
    """Check if an HTTP endpoint is ready (2xx/3xx).

    4xx/5xx means the listener answered but is not ready — e.g. ``/health``
    returning 500 must not report ``kernel_serve`` as healthy.
    """
    curl = resolve_probe_cmd("curl")
    try:
        r = subprocess.run(  # noqa: S603 -- internal probe url with timeout
            [
                curl,
                "--noproxy",
                "*",
                "-sS",
                "--max-time",
                str(timeout),
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            timeout=timeout + 1,
            text=True,
        )
        if r.returncode != 0:
            return False
        code = int((r.stdout or "").strip())
        return 200 <= code < 400
    except Exception:
        # INTENTIONAL: HTTP 检查失败 → 回 False;这是 readiness probe,
        # caller 会重试或报错,不阻断启动流程。
        return False


def http_code(url: str, timeout: float = 2.0) -> int:
    """Return the HTTP status code for ``url``, or 0 when unreachable.

    Same probe shape as ``http_ready`` but returns the raw code instead of
    the 2xx/3xx boolean. Used by checks that must require exactly 200 (e.g.
    the LobeHub route-integrity probe: ``/signin`` answering a redirect means
    the dev route table collapsed, which ``http_ready`` would miss).
    """
    curl = resolve_probe_cmd("curl")
    try:
        r = subprocess.run(  # noqa: S603 -- internal probe url with timeout
            [
                curl,
                "--noproxy",
                "*",
                "-sS",
                "--max-time",
                str(timeout),
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            timeout=timeout + 1,
            text=True,
        )
        if r.returncode != 0:
            return 0
        return int((r.stdout or "").strip())
    except Exception:
        # INTENTIONAL: 探针失败视为不可达(0),由 caller 决定如何归类。
        return 0


def health_body_ok(url: str, timeout: float = 2.0) -> bool:
    """Return True iff ``GET url`` returns 200 AND body JSON has ``status == "ok"``.

    Used by ``KernelServeService.state()`` for kernel health projection
    after ADR-0213 PR-2: ``/health`` body now carries
    ``{status, runs, live, event_bus, plugin}``. A 200 with body
    ``{"status": "degraded"}`` (e.g. event_bus dropped_total > 0) or
    ``{"status": "loading"}`` (boot in progress) must NOT report
    ``kernel_serve`` as ready. This is the explicit post-0213 check; the
    original ``http_ready`` retains its 2xx/3xx semantics for non-health
    probes.
    """
    curl = resolve_probe_cmd("curl")
    try:
        r = subprocess.run(  # noqa: S603 -- internal probe url with timeout
            [
                curl,
                "-sS",
                "--max-time",
                str(timeout),
                "-w",
                "\n%{http_code}",
                url,
            ],
            capture_output=True,
            timeout=timeout + 1,
            text=True,
        )
        if r.returncode != 0:
            return False
        out = r.stdout or ""
        sep = out.rfind("\n")
        if sep == -1:
            return False
        body = out[:sep]
        try:
            code = int(out[sep + 1 :].strip())
        except ValueError:
            return False
        if code != 200:
            return False
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        return parsed.get("status") == "ok"
    except Exception:
        return False
