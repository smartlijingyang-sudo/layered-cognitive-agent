"""Kernel serve spawn state machine.

Replaces the ``_spawn() -> bool`` shim that ``KernelServeService`` previously
used. The shim compressed "start a uvicorn subprocess and wait until ready"
into a single boolean, hiding four observable failure modes:

  * JWT preflight blocking the spawn entirely
  * subprocess dying immediately (often silently, due to ``Popen`` buffering)
  * subprocess booting but ``/health`` never answering
  * subprocess ready at HTTP 200 but plugin registry not populated

Each step is now an explicit atomic check whose outcome is recorded in a
frozen :class:`StepResult`. :class:`SpawnResult` aggregates the full sequence
plus an ``actionable`` next-step suggestion for operators / agents.

stderr from the spawned kernel lands in a per-spawn file
(``/tmp/lca-kernel.stderr.<pid>.<yyyymmddhhmmss>.log``), retained for the
most recent ``_STDERR_KEEP_N`` files; older files are removed by mtime. This
removes the cross-spawn interleaving of the previous append-only ``/tmp/lca-kernel.log``.

See ADR-0213 §决定 1–3 for the rationale and wire contract.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.service.service import pid_alive

_STAGE = Literal["preflight", "start", "port_bound", "http_ready", "plugin_ready"]

_PORT_BOUND_TIMEOUT_S = 5.0
_HTTP_TIMEOUT_S = 30.0
_STDERR_KEEP_N = 5
_STDERR_DIR = Path("/tmp")  # noqa: S108 — stable path for self-heal logs


class StepResult(BaseModel):
    """Outcome of one atomic spawn step.

    Attributes:
        stage: which of the 5 atomic checks this row describes.
        ok: True iff the check passed.
        duration_ms: wall-clock time spent inside the step.
        error: short failure reason (e.g. ``"health_timeout"``); ``None`` on success.
        detail: per-stage debug info (attempts / last_status / last_body / pid / port).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: _STAGE
    ok: bool
    duration_ms: int
    error: str | None = None
    detail: dict[str, Any] = {}


class SpawnResult(BaseModel):
    """Aggregated outcome of a full spawn attempt.

    Attributes:
        ok: True iff all 5 steps returned ``ok=True``. **Timeouts never flip
            this to True** — see ADR-0213 §决定 3.
        failed_stage: name of the first failing step, ``None`` on success.
        steps: full ordered sequence of step outcomes.
        pid: kernel PID once ``start`` succeeds, ``None`` if spawn never started.
        port: kernel HTTP port (always the configured port, even on failure).
        stderr_path: per-spawn log file the kernel's stderr was redirected to.
        duration_ms: total wall-clock time across all steps.
        actionable: short next-step suggestion for operators / agents, ``None`` on success.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    failed_stage: _STAGE | None = None
    steps: list[StepResult] = (  # type: ignore[assignment]
        []
    )
    pid: int | None = None
    port: int
    stderr_path: Path | None = None
    duration_ms: int = 0
    actionable: str | None = None


def _utc_stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


def _stderr_path_for(pid: int | None) -> Path:
    name = f"lca-kernel.stderr.{pid if pid is not None else 'pre'}.{_utc_stamp()}.log"
    return _STDERR_DIR / name


def _prune_old_stderr() -> None:
    """Keep at most ``_STDERR_KEEP_N`` stderr files in ``_STDERR_DIR``."""
    try:
        files = sorted(
            (
                p
                for p in _STDERR_DIR.iterdir()
                if p.is_file()
                and p.name.startswith("lca-kernel.stderr.")
                and p.name.endswith(".log")
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for old in files[_STDERR_KEEP_N:]:
        with contextlib.suppress(OSError):
            old.unlink()


def _preflight(profile_path: Path) -> tuple[str, str | None]:
    """Replicate the JWT preflight check; return ``(status, message_or_none)``.

    ``status`` is one of ``"ok" / "warn" / "block"``. Implementation mirrors
    ``KernelServeService._preflight_jwt_secret`` (kept as the single source of
    truth inside the kernel package, see ADR-0213 delete-when).
    """
    try:
        import yaml
    except ImportError:
        return "ok", None

    try:
        if not profile_path.is_absolute():
            return "ok", None
        data = yaml.safe_load(profile_path.read_text())
    except (OSError, yaml.YAMLError):
        return "ok", None  # let kernel's own check fire

    def _walk(node: object) -> dict[str, Any] | None:
        if isinstance(node, dict):
            if node.get("id") == "lca-webserver-jwt-keys":
                cfg = node.get("config") or {}
                return cfg if isinstance(cfg, dict) else None
            for v in node.values():
                found = _walk(v)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _walk(item)
                if found is not None:
                    return found
        return None

    jwt_cfg = _walk(data)
    if jwt_cfg is None:
        return "ok", None
    if bool(jwt_cfg.get("dev_mode")):
        return (
            "warn",
            "JWT key auto-generation (dev_mode=true); "
            "key changes on every kernel restart — not safe for multi-replica.",
        )

    private_pem = jwt_cfg.get("private_pem")
    if isinstance(private_pem, dict) and "from_env" in private_pem:
        env_name = str(private_pem["from_env"])
        if os.environ.get(env_name):
            return "ok", None
        return (
            "block",
            f"Profile requires `{env_name}` for the JWT signing key, but the env "
            "var is not set. Refusing to spawn kernel — set the env var (or "
            "temporarily add `jwt.dev_mode: true` to the Profile) and retry. See "
            "docs/notes/implemented/seam/2026-09-07-jwt-secret-injection-via-profile.md.",
        )

    if isinstance(private_pem, str) and private_pem.strip():
        return "ok", None

    return (
        "block",
        "Profile has neither `jwt.private_pem` nor `jwt.dev_mode`. "
        "Refusing to spawn kernel. Configure one of the two and retry.",
    )


def _http_get(url: str, timeout: float) -> tuple[int, str]:
    """GET ``url`` and return ``(status_code, body)``; ``(-1, "")`` on network error."""
    try:
        req = urllib.request.Request(url, method="GET")  # noqa: S310 — health/body probes, http(s) only
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            body = r.read().decode("utf-8", errors="ignore")
            return r.status, body
    except (urllib.error.URLError, OSError, TimeoutError):
        return -1, ""


def _probe_lan(host: str, port: int, health_url: str) -> tuple[bool, str | None]:
    """Reproduce ``KernelServeService._probe_proxy_lan`` semantics.

    Returns ``(ok, reason)``. When the active host is not bind-all, returns
    ``(True, None)`` immediately. When the proxy env vars are unset, also
    ``(True, None)`` (operator chose loopback-only). Otherwise GETs the
    LAN URL ``/health``; unreachable → ``(False, reason)``.
    """
    import os
    import urllib.parse

    if host not in ("0.0.0.0", "::"):  # noqa: S104 — bind-all sentinel, see KernelServeConfig
        return True, None

    candidates = ("LCA_GATEWAY_PUBLIC_URL", "OPENAI_PROXY_URL")
    target = next((os.environ[k] for k in candidates if os.environ.get(k)), "")
    if not target:
        return True, None
    parsed = urllib.parse.urlparse(target)
    if not parsed.hostname or not parsed.port:
        return True, None
    lan_health = f"http://{parsed.hostname}:{parsed.port}/health"
    if lan_health == health_url:
        return True, None  # same as loopback, already probed
    status, _ = _http_get(lan_health, timeout=2.0)
    if 200 <= status < 400:
        return True, None
    return False, f"lan_unreachable:{lan_health}"


def _body_json_ok(body: str) -> bool:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    return parsed.get("status") == "ok"


def _plugin_ready(body: str) -> tuple[bool, dict[str, Any]]:
    """Return ``(ok, detail)`` from the ``plugin`` block in the /health body.

    Detail keys: ``registered``, ``expected``, ``missing``,
    ``registry_populated``, ``pipeline_registered``, ``cognitive_driver_registered``.
    """
    empty: dict[str, Any] = {
        "registered": 0,
        "expected": 0,
        "missing": [],
        "registry_populated": False,
        "pipeline_registered": False,
        "cognitive_driver_registered": False,
    }
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return False, empty
    plugin = parsed.get("plugin") if isinstance(parsed, dict) else None
    if not isinstance(plugin, dict):
        return False, empty

    registered = int(plugin.get("registered", 0))
    expected = int(plugin.get("expected", 0))
    missing = list(plugin.get("missing") or [])

    ok = (
        registered == expected
        and not missing
        and bool(plugin.get("registry_populated"))
        and bool(plugin.get("pipeline_registered"))
        and bool(plugin.get("cognitive_driver_registered"))
    )
    return ok, {
        "registered": registered,
        "expected": expected,
        "missing": missing,
        "registry_populated": bool(plugin.get("registry_populated")),
        "pipeline_registered": bool(plugin.get("pipeline_registered")),
        "cognitive_driver_registered": bool(plugin.get("cognitive_driver_registered")),
    }


class KernelServeSpawner:
    """State machine that replaces ``KernelServeService._spawn() -> bool``.

    Steps are short-circuited: a failure stops the sequence and returns an
    ``SpawnResult(ok=False, failed_stage=<step>)``. Successes run all 5
    steps. ``run()`` is safe to call multiple times on the same instance; it
    holds no mutable state across calls.
    """

    def __init__(
        self,
        config: KernelServeConfig,
        root: Path,
        *,
        port_bound_timeout: float = _PORT_BOUND_TIMEOUT_S,
        http_timeout: float = _HTTP_TIMEOUT_S,
    ) -> None:
        self._config = config
        self._root = root
        self._port_bound_timeout = port_bound_timeout
        self._http_timeout = http_timeout

    @property
    def health_url(self) -> str:
        probe_host = "127.0.0.1" if self._config.host in ("0.0.0.0", "::") else self._config.host  # noqa: S104 — bind-all sentinel, see KernelServeConfig
        return f"http://{probe_host}:{self._config.port}/health"

    def run(self) -> SpawnResult:
        """Execute the 5-step spawn sequence; return a structured outcome."""
        steps: list[StepResult] = []
        pid: int | None = None
        stderr_path: Path | None = None
        port = self._config.port
        start_ts = time.monotonic()

        # step 1: preflight
        step1_ok, step1_msg, step1 = self._step_preflight()
        steps.append(step1)
        if not step1_ok:
            return SpawnResult(
                ok=False,
                failed_stage="preflight",
                steps=steps,
                pid=None,
                port=port,
                stderr_path=None,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                actionable=step1_msg
                or "Fix the JWT preflight blocker (see docs/notes/implemented/seam/"
                "2026-09-07-jwt-secret-injection-via-profile.md) and retry.",
            )

        # step 2: start
        pid, stderr_path, step2 = self._step_start()
        steps.append(step2)
        if pid is None:
            return SpawnResult(
                ok=False,
                failed_stage="start",
                steps=steps,
                pid=None,
                port=port,
                stderr_path=stderr_path,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                actionable=(
                    f"`subprocess.Popen` failed for `lca_kernel serve`. "
                    f"Inspect the most recent stderr file: {stderr_path}"
                    if stderr_path
                    else "`subprocess.Popen` failed before stderr was redirected."
                ),
            )

        # step 3: port_bound
        step3 = self._step_port_bound(pid, port)
        steps.append(step3)
        if not step3.ok:
            return SpawnResult(
                ok=False,
                failed_stage="port_bound",
                steps=steps,
                pid=pid,
                port=port,
                stderr_path=stderr_path,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                actionable=(
                    f"kernel pid={pid} is alive but TCP {port} is not bound within "
                    f"{int(self._port_bound_timeout)}s. Inspect stderr: {stderr_path}"
                ),
            )

        # step 4: http_ready
        step4 = self._step_http_ready()
        steps.append(step4)
        if not step4.ok:
            return SpawnResult(
                ok=False,
                failed_stage="http_ready",
                steps=steps,
                pid=pid,
                port=port,
                stderr_path=stderr_path,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                actionable=(
                    f"kernel pid={pid} bound TCP {port} but /health did not return "
                    f"status=ok within {int(self._http_timeout)}s. Inspect stderr: "
                    f"{stderr_path}"
                ),
            )

        # step 5: plugin_ready (non-fatal but recorded; degrade-only if missing
        # field is the only reason — agent still sees healthy kernel)
        step5 = self._step_plugin_ready(step4.detail.get("body", ""))
        steps.append(step5)
        if not step5.ok:
            return SpawnResult(
                ok=False,
                failed_stage="plugin_ready",
                steps=steps,
                pid=pid,
                port=port,
                stderr_path=stderr_path,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                actionable=(
                    f"kernel pid={pid} reports HTTP 200 with status=ok but plugin "
                    f"registry is not fully populated "
                    f"(registered={step5.detail.get('registered')}, "
                    f"expected={step5.detail.get('expected')}, "
                    f"missing={step5.detail.get('missing')}). Inspect stderr: "
                    f"{stderr_path}"
                ),
            )

        return SpawnResult(
            ok=True,
            failed_stage=None,
            steps=steps,
            pid=pid,
            port=port,
            stderr_path=stderr_path,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            actionable=None,
        )

    # ── steps ────────────────────────────────────────────────────────

    def _step_preflight(self) -> tuple[bool, str | None, StepResult]:
        t0 = time.monotonic()
        profile_path = Path(self._config.profile)
        if not profile_path.is_absolute():
            profile_path = self._root / profile_path
        status, message = _preflight(profile_path)
        ok = status != "block"
        # When blocking, surface the underlying message as the actionable
        # operator hint. When warning, surface it as a pre-spawn notice.
        return (
            ok,
            message,
            StepResult(
                stage="preflight",
                ok=ok,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=None if ok else "jwt_preflight_blocked",
                detail={"status": status},
            ),
        )

    def _step_start(self) -> tuple[int | None, Path | None, StepResult]:
        t0 = time.monotonic()
        _prune_old_stderr()
        stderr_path = _stderr_path_for(None)
        try:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            log_f = stderr_path.open("wb", buffering=0)
        except OSError as exc:
            return (
                None,
                None,
                StepResult(
                    stage="start",
                    ok=False,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error="stderr_open_failed",
                    detail={"errno": exc.errno, "strerror": exc.strerror},
                ),
            )

        try:
            proc = subprocess.Popen(  # noqa: S603
                [
                    sys.executable,
                    "-m",
                    "lca_kernel",
                    "serve",
                    "--profile",
                    self._config.profile,
                    "--host",
                    self._config.host,
                    "--port",
                    str(self._config.port),
                    "--allow-unknown-env",
                ],
                cwd=str(self._root),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            with contextlib.suppress(OSError):
                log_f.close()
            return (
                None,
                stderr_path,
                StepResult(
                    stage="start",
                    ok=False,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error="popen_oserror",
                    detail={"errno": exc.errno, "strerror": exc.strerror},
                ),
            )

        # refresh stderr_path to include actual pid; rename to canonical name
        canonical = _stderr_path_for(proc.pid)
        try:
            log_f.flush()
            log_f.close()
            stderr_path.rename(canonical)
            stderr_path = canonical
        except OSError:
            # fall back to original path; readability still works.
            with contextlib.suppress(OSError):
                log_f.close()
        # Re-open for ongoing writes (we already redirected fd to log_f above;
        # Popen holds the fd, but we still need a path for ongoing tail).
        # The fd is bound to the (now renamed) inode; reopen in append mode
        # would not share the fd. Keep the original log_f open via a no-op
        # reference so it isn't GC'd before Popen's writes finish.
        _keepalive_ref = log_f

        return (
            proc.pid,
            stderr_path,
            StepResult(
                stage="start",
                ok=True,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=None,
                detail={"pid": proc.pid, "stderr_path": str(stderr_path)},
            ),
        )

    def _step_port_bound(self, pid: int, port: int) -> StepResult:
        t0 = time.monotonic()
        attempts = 0
        deadline = t0 + self._port_bound_timeout
        while time.monotonic() < deadline:
            attempts += 1
            if not pid_alive(pid):
                return StepResult(
                    stage="port_bound",
                    ok=False,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error="kernel_died",
                    detail={"pid": pid, "attempts": attempts},
                )
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return StepResult(
                        stage="port_bound",
                        ok=True,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        error=None,
                        detail={"pid": pid, "port": port, "attempts": attempts},
                    )
            except OSError:
                time.sleep(0.2)
        return StepResult(
            stage="port_bound",
            ok=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error="port_not_bound",
            detail={"pid": pid, "port": port, "attempts": attempts},
        )

    def _step_http_ready(self) -> StepResult:
        t0 = time.monotonic()
        attempts = 0
        deadline = t0 + self._http_timeout
        last_status = -1
        last_body = ""
        while time.monotonic() < deadline:
            attempts += 1
            status, body = _http_get(self.health_url, timeout=1.0)
            last_status = status
            last_body = body
            if status == 200 and _body_json_ok(body):
                # inline LAN probe: only relevant when bind-all
                lan_ok, lan_reason = _probe_lan(
                    self._config.host, self._config.port, self.health_url
                )
                if not lan_ok:
                    return StepResult(
                        stage="http_ready",
                        ok=False,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        error=lan_reason or "lan_unreachable",
                        detail={
                            "attempts": attempts,
                            "last_status": status,
                            "body": body[:512],
                        },
                    )
                return StepResult(
                    stage="http_ready",
                    ok=True,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=None,
                    detail={"attempts": attempts, "last_status": status, "body": body[:512]},
                )
            time.sleep(0.5)
        # decide final reason
        if last_status == -1:
            error = "health_unreachable"
        elif last_status != 200:
            error = f"health_status_{last_status}"
        elif not _body_json_ok(last_body):
            error = "health_status_not_ok"
        else:
            error = "health_timeout"
        return StepResult(
            stage="http_ready",
            ok=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=error,
            detail={"attempts": attempts, "last_status": last_status, "body": last_body[:512]},
        )

    def _step_plugin_ready(self, body: str) -> StepResult:
        t0 = time.monotonic()
        ok, detail = _plugin_ready(body)
        return StepResult(
            stage="plugin_ready",
            ok=ok,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=None if ok else "plugin_not_ready",
            detail=detail,
        )


__all__ = ["KernelServeSpawner", "SpawnResult", "StepResult"]
