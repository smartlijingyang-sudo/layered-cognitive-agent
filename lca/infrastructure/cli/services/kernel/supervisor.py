"""Kernel supervisor — minimal supervisord-style process manager.

Why this exists
---------------
LCA's kernel in production is guarded by an external supervisor (ADR-0119).
For the **dev path**, ``lca-ops`` still needs a way to spawn / stop /
restart the kernel locally without each user wiring up supervisord or
systemd. This module is that local supervisor: a small
``KernelSupervisor`` that owns the kernel subprocess, runs an
autorestart loop, and surfaces events to ``lca-ops`` CLI consumers.

Design
------
Three independent loops, each doing one thing:

1. ``spawner`` — call :func:`subprocess.Popen` + emit ``spawned`` event.
2. ``waiter`` — call :func:`proc.wait` (blocking, no busy-poll) +
   emit ``died`` event with exit code.
3. ``decider`` — pull ``died`` events, call :func:`decide_restart`
   (pure function, table-driven) and emit ``restarted`` / ``fatal`` /
   ``stopped`` events.

State is a single :class:`ProgramState` value, mutated only via
:meth:`transition`, which fires the event and wakes subscribers.

Readiness
---------
After spawning, a one-shot ``GET /health`` probe (via
:func:`health_body_ok`) is attempted every :attr:`_READINESS_POLL_S`
until it succeeds or :attr:`ProgramConfig.readiness_timeout` elapses.
A timeout does **not** kill the subprocess; it just leaves state at
STARTING. Death while STARTING triggers the decider.

Why no busy-poll
----------------
:func:`proc.wait` blocks until the kernel exits; no need for
``while poll() is None: sleep(0.1)``. :func:`queue.Queue.get` blocks
until an event is queued; no need for ``while True: check``.
"""

from __future__ import annotations

import configparser
import contextlib
import enum

# ── State file (cross-process singleton) ────────────────────────────────
# Each CLI invocation is a fresh process; the supervisor's ``_proc`` /
# ``_state`` live only inside that process. The state file lets
# ``status`` (in process A) read what ``start`` (in process B) wrote.
# Format is JSON, atomic write via tmp + rename.
import json as _json
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lca.infrastructure.cli.service.service import health_body_ok

_STATE_PATH = Path(
    os.environ.get(
        "LCA_SUPERVISOR_STATE", "/tmp/lca-supervisor.state.json"  # noqa: S108
    )
)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: tmp + rename, so readers never see a torn
    file. Best-effort; readers fall back to "unknown" on read failure.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(_json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def read_state_file() -> dict | None:
    """Public read of the cross-process state file.

    Returns the parsed dict written by the most recent
    :meth:`KernelSupervisor._transition`, or ``None`` if the file is
    missing / unreadable / malformed.
    """
    return _read_state_file()


def _read_state_file() -> dict | None:
    """Best-effort read of the supervisor state file."""
    try:
        return _json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_state(name: str, snapshot: ProgramStatus) -> None:
    _atomic_write_json(
        _STATE_PATH,
        {
            "program": name,
            "pid": snapshot.pid,
            "state": snapshot.state.value,
            "uptime_s": snapshot.uptime_s,
            "restart_count": snapshot.restart_count,
            "last_exit_code": snapshot.last_exit_code,
            "last_event": snapshot.last_event,
            "spawned_at": snapshot.spawned_at,
            "ts": time.time(),
        },
    )


def clear_state() -> None:
    """Delete the cross-process state file. Idempotent."""
    with contextlib.suppress(OSError):
        _STATE_PATH.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# Per-process cache of supervisor instances, keyed by config fingerprint.
# Lives in the service module so both ``kernel-supervisor`` and
# ``kernel-restart`` (CLI) reuse the same instance when invoked from
# the same Python process. Cross-process state is the JSON state file.
_SUPERVISOR_CACHE: dict[str, KernelSupervisor] = {}


class _PhantomProc:
    """Stand-in for :class:`subprocess.Popen` when the supervisor was
    hydrated from a state file written by a previous process.

    Forwards signals; the only real subprocess work happens in a future
    ``start()`` call. The methods ``wait`` / ``poll`` are needed because
    :meth:`KernelSupervisor.stop` talks to the proc the same way it
    would to a real ``Popen`` — keeps the supervisor's surface
    uniform across the in-process and hydrated cases.
    """

    __slots__ = ("_pid",)

    def __init__(self, pid: int) -> None:
        self._pid = pid

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        try:
            os.kill(self._pid, 0)
        except OSError:
            return -1
        return None

    def send_signal(self, sig: int) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(self._pid, sig)

    def wait(self, timeout: float | None = None) -> int:
        deadline = time.monotonic() + (timeout or 10.0)
        while time.monotonic() < deadline:
            try:
                waited_pid, status = os.waitpid(self._pid, os.WNOHANG)
                if waited_pid == self._pid:
                    return os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                return -1
            time.sleep(0.1)
        raise subprocess.TimeoutExpired(self._pid, timeout)


def _hydrate_from_state_file(sup: KernelSupervisor, cfg: ProgramConfig) -> None:
    """Read the most recent state-file snapshot and apply it to ``sup``
    IF the persisted pid is still alive. Called from
    :func:`get_supervisor` on first use within a process.
    """
    st = read_state_file()
    if st is None or st.get("program") != cfg.name:
        return
    persisted_pid = st.get("pid")
    if persisted_pid is None or not _pid_alive(int(persisted_pid)):
        clear_state()
        return
    sup._state = ProgramState(st["state"])
    sup._last_event = st.get("last_event", "")
    sup._restart_count = st.get("restart_count", 0)
    sup._last_exit_code = st.get("last_exit_code")
    sup._spawned_at = time.monotonic()  # reset the clock for this process
    sup._proc = _PhantomProc(int(persisted_pid))


def get_supervisor(cfg: ProgramConfig) -> KernelSupervisor:
    """One canonical supervisor per (config fingerprint) per process.

    Hydrates from the cross-process state file on first use so a
    status / restart in a fresh CLI invocation sees what the previous
    process wrote. The kernel spawn / event loop work lives in
    :class:`KernelSupervisor`; this function is only the
    "find-or-create + hydrate" entry point.
    """
    key = f"{cfg.name}:{cfg.directory}:{cfg.command}:{cfg.args}"
    sup = _SUPERVISOR_CACHE.get(key)
    if sup is not None:
        return sup
    sup = KernelSupervisor(cfg)
    _SUPERVISOR_CACHE[key] = sup
    _hydrate_from_state_file(sup, cfg)
    return sup


def status_from_state_file(cfg: ProgramConfig) -> ProgramStatus | None:
    """Read the persisted snapshot, returning ``None`` if the state
    file is missing or refers to a different program.
    """
    st = read_state_file()
    if st is None or st.get("program") != cfg.name:
        return None
    try:
        state = ProgramState(st["state"])
    except (KeyError, ValueError):
        return None
    return ProgramStatus(
        name=cfg.name,
        state=state,
        pid=st.get("pid"),
        uptime_s=st.get("uptime_s", 0.0),
        restart_count=st.get("restart_count", 0),
        last_exit_code=st.get("last_exit_code"),
        last_event=st.get("last_event", ""),
        spawned_at=st.get("spawned_at"),
    )


# ── Action result builders ─────────────────────────────────────────────
#
# Every action (start, stop, restart, status, events, logs, check-config)
# returns the same shape — a dict with verdict / detail / status / events
# / next_command keys. Builders live here so service-layer tests can
# pin the wire contract without touching the CLI dispatcher.


def _status_dict(status: ProgramStatus) -> dict[str, Any]:
    return {
        "name": status.name,
        "state": status.state.value,
        "pid": status.pid,
        "uptime_s": round(status.uptime_s, 2),
        "restart_count": status.restart_count,
        "last_exit_code": status.last_exit_code,
        "last_event": status.last_event,
        "spawned_at": status.spawned_at,
    }


def _events_dict(events) -> list[dict[str, Any]]:
    return [
        {
            "ts": e.ts,
            "kind": e.kind,
            "pid": e.pid,
            "exit_code": e.exit_code,
            "message": e.message,
        }
        for e in events
    ]


def build_start_result(
    cfg: ProgramConfig, status: ProgramStatus, *, ready: bool,
) -> dict[str, Any]:
    """Result of ``start`` action.

    ``ready=True`` → verdict=ready, next_command points to status.
    ``ready=False`` → verdict=failed, next_command points to logs.
    """
    if ready:
        return {
            "verdict": "ready",
            "detail": (
                f"supervisor started pid={status.pid} "
                f"uptime={status.uptime_s:.1f}s"
            ),
            "status": _status_dict(status),
            "next_command": (
                f"./scripts/lca-ops kernel-supervisor status --name {cfg.name}"
            ),
        }
    return {
        "verdict": "failed",
        "detail": (
            f"supervisor start did not become ready within "
            f"{cfg.readiness_timeout}s: {status.last_event}"
        ),
        "status": _status_dict(status),
        "next_command": (
            f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
        ),
    }


def build_stop_result(
    cfg: ProgramConfig, status: ProgramStatus, *, orphans_killed: int,
) -> dict[str, Any]:
    return {
        "verdict": "ready",
        "detail": (
            f"supervisor stopped (exit_code={status.last_exit_code}, "
            f"orphans_killed={orphans_killed})"
        ),
        "status": _status_dict(status),
        "next_command": (
            f"./scripts/lca-ops kernel-supervisor start --name {cfg.name}"
        ),
    }


def build_restart_result(
    cfg: ProgramConfig, status: ProgramStatus, *, ready: bool,
) -> dict[str, Any]:
    if ready:
        return {
            "verdict": "ready",
            "detail": (
                f"LCA kernel restarted (pid={status.pid}, "
                f"restart_count={status.restart_count})"
            ),
            "status": _status_dict(status),
            "next_command": (
                f"./scripts/lca-ops kernel-supervisor status --name {cfg.name}"
            ),
        }
    return {
        "verdict": "failed",
        "detail": (
            f"restart did not become ready within "
            f"{cfg.readiness_timeout}s: {status.last_event}"
        ),
        "status": _status_dict(status),
        "next_command": (
            f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
        ),
    }


def build_status_result(
    cfg: ProgramConfig,
    status: ProgramStatus,
    *,
    events,
    is_fatal: bool = False,
) -> dict[str, Any]:
    verdict = "ready"
    if is_fatal or status.state == ProgramState.FATAL:
        verdict = "failed"
    payload: dict[str, Any] = {
        "verdict": verdict,
        "status": _status_dict(status),
        "events": _events_dict(events),
    }
    if is_fatal or status.state == ProgramState.FATAL:
        payload["next_command"] = (
            f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
        )
    return payload


def build_events_result(events) -> dict[str, Any]:
    return {"verdict": "ready", "events": _events_dict(events)}


def build_check_config_result(
    config_path: str | Path, programs: list[ProgramConfig],
) -> dict[str, Any]:
    return {
        "verdict": "ready",
        "config_path": str(config_path),
        "programs": [
            {
                "name": p.name,
                "argv_head": p.argv()[:3],
                "host": p.host(),
                "port": p.port(),
                "autorestart": p.autorestart,
                "startretries": p.startretries,
            }
            for p in programs
        ],
    }


def build_config_error_result(
    config_path: str | Path, exc: Exception,
) -> dict[str, Any]:
    return {
        "verdict": "failed",
        "reason": f"config invalid: {exc}",
        "next_command": (
            f"./scripts/lca-ops kernel-supervisor check-config "
            f"--config {config_path}"
        ),
    }


def build_command_error_result(
    action: str,
    cfg: ProgramConfig | None,
    *,
    orphan_pids: list[int] | None = None,
    status: ProgramStatus | None = None,
) -> dict[str, Any]:
    """Result of an unsupported action / pre-condition failure."""
    if orphan_pids and cfg is not None:
        return {
            "verdict": "failed",
            "reason": (
                f"kernel already running (pid={orphan_pids}); refusing "
                f"double-spawn. Run `./scripts/lca-ops kernel-supervisor "
                f"stop` first or SIGTERM the orphan."
            ),
            "status": _status_dict(status) if status is not None else None,
            "next_command": (
                f"./scripts/lca-ops kernel-supervisor stop --name {cfg.name}"
            ),
        }
    return {
        "verdict": "failed",
        "reason": f"unknown action {action!r}",
        "next_command": "./scripts/lca-ops kernel-supervisor --help",
    }


# ── Public types ────────────────────────────────────────────────────────


class ProgramState(str, enum.Enum):
    """Lifecycle state of one supervised program.

    String-valued so :class:`ProgramStatus` serialises naturally in
    JSON without a custom encoder; values are stable across the wire.
    """

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    BACKOFF = "backoff"
    FATAL = "fatal"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ProgramConfig:
    """One ``[program:...]`` section, supervisord-compatible keys.

    Mirrors supervisord's vocabulary (subset). Unknown keys raise
    :class:`ValueError` at parse time so mis-typed config fails loud.
    """

    name: str
    command: str
    directory: str = ""
    autorestart: bool = True
    startretries: int = 3
    stopwaitsecs: float = 15.0
    environment: dict[str, str] = field(default_factory=dict)
    stdout_logfile: str | None = None
    stderr_logfile: str | None = None
    readiness_timeout: float = 30.0
    args: tuple[str, ...] = field(default_factory=tuple)

    def argv(self) -> list[str]:
        cmd = shlex.split(self.command) if self.command else []
        return cmd + list(self.args)

    def host(self) -> str:
        for i, a in enumerate(self.args):
            if a == "--host" and i + 1 < len(self.args):
                return self.args[i + 1]
        return "127.0.0.1"

    def port(self) -> int | None:
        for i, a in enumerate(self.args):
            if a == "--port" and i + 1 < len(self.args):
                try:
                    return int(self.args[i + 1])
                except ValueError:
                    return None
        return None


@dataclass(frozen=True)
class ProgramEvent:
    """One supervisor event, emitted on the event stream.

    ``kind`` ∈ ``{spawned, ready, died, restarted, stopped, fatal,
    backoff}``. ``message`` is human-readable; consumers should not
    parse it.
    """

    ts: float
    kind: str
    pid: int | None = None
    exit_code: int | None = None
    message: str = ""


@dataclass(frozen=True)
class ProgramStatus:
    """Snapshot of a supervised program at one moment in time."""

    name: str
    state: ProgramState
    pid: int | None = None
    uptime_s: float = 0.0
    restart_count: int = 0
    last_exit_code: int | None = None
    last_event: str = ""
    spawned_at: float | None = None


# ── Restart-decision table (pure, table-driven) ────────────────────────


@dataclass(frozen=True)
class RestartDecision:
    """Outcome of :func:`decide_restart`."""

    next_state: ProgramState
    backoff_s: float
    reason: str


# Supervisord-aligned "clean" exit codes (0 = clean, 2 = SIGINT, 3 = SIGQUIT).
_EXIT_CLEAN = frozenset({0, 2, 3})


def decide_restart(
    exit_code: int,
    *,
    autorestart: bool,
    restart_count: int,
    startretries: int,
    user_stopped: bool,
) -> RestartDecision:
    """Pure decision function — table-driven, no I/O, easy to test.

    Rules (mirrors supervisord's expected/unexpected exit semantics):
    1. user_stopped → STOPPED (no autorestart, no matter what).
    2. clean exit + autorestart=False → STOPPED.
    3. exhausted startretries → FATAL.
    4. anything else → BACKOFF with exponential backoff.
    """
    if user_stopped:
        return RestartDecision(ProgramState.STOPPED, 0.0, "user stop")
    clean = exit_code in _EXIT_CLEAN
    if clean and not autorestart:
        return RestartDecision(
            ProgramState.STOPPED, 0.0, "clean exit, autorestart=false"
        )
    if restart_count >= startretries:
        return RestartDecision(
            ProgramState.FATAL,
            0.0,
            f"exhausted startretries={startretries} after exit={exit_code}",
        )
    backoff = min(2 ** restart_count, 30.0)
    return RestartDecision(
        ProgramState.BACKOFF,
        backoff,
        f"retry {restart_count + 1}/{startretries} after exit={exit_code}",
    )


# ── Configparser loader (supervisord syntax) ────────────────────────────


_TRUE = {"true", "yes", "1"}
_FALSE = {"false", "no", "0"}


def _parse_bool(raw: str, key: str) -> bool:
    lo = raw.strip().lower()
    if lo in _TRUE:
        return True
    if lo in _FALSE:
        return False
    raise ValueError(f"{key}: expected true/false/yes/no/1/0, got {raw!r}")


def _parse_int(raw: str, key: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key}: expected integer, got {raw!r}") from exc


def _parse_float(raw: str, key: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key}: expected number, got {raw!r}") from exc


def _parse_env(raw: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"environment: expected KEY=VAL pairs, got {part!r}")
        k, v = part.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"environment: empty key in {part!r}")
        env[k] = v.strip()
    return env


def parse_program_config(path: str | Path) -> list[ProgramConfig]:
    """Parse a supervisord-style config file into a list of programs."""
    parser = configparser.ConfigParser()
    parser.allow_no_value = False
    read = parser.read(path, encoding="utf-8")
    if not read:
        raise ValueError(f"config file unreadable or empty: {path}")

    programs: list[ProgramConfig] = []
    known_keys = {
        "command", "args", "directory", "autorestart", "startretries",
        "stopwaitsecs", "environment", "stdout_logfile", "stderr_logfile",
        "readiness_timeout",
    }
    for section in parser.sections():
        if not section.startswith("program:"):
            continue
        name = section[len("program:"):].strip()
        if not name:
            raise ValueError(f"{section}: empty program name")
        items = dict(parser.items(section))

        unknown = set(items) - known_keys
        if unknown:
            raise ValueError(
                f"[program:{name}]: unknown keys: {sorted(unknown)}"
            )

        command = items.get("command", "")
        if not command:
            raise ValueError(f"[program:{name}]: command= is required")

        args_raw = items.get("args", "")
        args: tuple[str, ...] = tuple(shlex.split(args_raw)) if args_raw else ()

        programs.append(
            ProgramConfig(
                name=name,
                command=command,
                args=args,
                directory=items.get("directory", "") or os.getcwd(),
                autorestart=_parse_bool(
                    items.get("autorestart", "true"), "autorestart"
                ),
                startretries=_parse_int(
                    items.get("startretries", "3"), "startretries"
                ),
                stopwaitsecs=_parse_float(
                    items.get("stopwaitsecs", "15"), "stopwaitsecs"
                ),
                environment=(
                    _parse_env(items["environment"])
                    if "environment" in items
                    else {}
                ),
                stdout_logfile=items.get("stdout_logfile") or None,
                stderr_logfile=items.get("stderr_logfile") or None,
                readiness_timeout=_parse_float(
                    items.get("readiness_timeout", "30"),
                    "readiness_timeout",
                ),
            )
        )
    if not programs:
        raise ValueError(f"{path}: no [program:...] sections found")
    return programs


def default_program_config(
    *,
    profile: str = "profiles/web-standard.yaml",
    host: str = "0.0.0.0",  # noqa: S104 — bind-all default
    port: int = 8765,
) -> ProgramConfig:
    """Build the dev-default LCA program."""
    return ProgramConfig(
        name="lca_kernel_dev",
        command=sys.executable,
        args=(
            "-m", "lca_kernel", "serve",
            "--profile", profile,
            "--host", host,
            "--port", str(port),
            "--allow-unknown-env",
        ),
        directory=os.getcwd(),
        autorestart=True,
        startretries=3,
        stopwaitsecs=15.0,
        environment={},
        stdout_logfile="/tmp/lca-kernel.stdout.log",  # noqa: S108
        stderr_logfile="/tmp/lca-kernel.stderr.log",  # noqa: S108
        readiness_timeout=30.0,
    )


# ── KernelSupervisor ────────────────────────────────────────────────────


class KernelSupervisor:
    """One supervised LCA kernel subprocess.

    Three internal threads (spawner / waiter / decider), each does one
    thing and yields via blocking primitives (``proc.wait``,
    ``queue.get``) — no busy-poll. A single :class:`ProgramState`
    field is the only mutable shared state; transitions go through
    :meth:`_transition`, which atomically updates state + emits an
    event + wakes any waiters.
    """

    _READINESS_POLL_S = 0.5

    def __init__(self, config: ProgramConfig) -> None:
        self._config = config
        self._proc: subprocess.Popen[bytes] | None = None
        self._state: ProgramState = ProgramState.STOPPED
        self._restart_count = 0
        self._last_exit_code: int | None = None
        self._last_event = ""
        self._spawned_at: float | None = None

        # Event stream + readiness signal. Threads use these to block
        # on state transitions without polling.
        self._events: queue.Queue[ProgramEvent] = queue.Queue()
        self._state_changed = threading.Event()
        self._stop_event = threading.Event()
        self._readiness_tested = threading.Event()

        self._stdout_f: Any = None
        self._stderr_f: Any = None

        self._threads: list[threading.Thread] = []
        self._threads_lock = threading.Lock()
        self._state_mutex = threading.Lock()

    # ── public API ────────────────────────────────────────────────

    @property
    def config(self) -> ProgramConfig:
        return self._config

    @property
    def state(self) -> ProgramState:
        return self._state

    def start(self) -> ProgramStatus:
        """Spawn the subprocess; returns immediately. Three threads
        run until :meth:`stop` or FATAL.
        """
        if self._state in {ProgramState.RUNNING, ProgramState.STARTING}:
            return self.status()
        self._open_log_files()
        argv = self._config.argv()
        cwd = self._config.directory or None
        env = (
            {**os.environ, **self._config.environment}
            if self._config.environment
            else None
        )
        try:
            proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
                argv,
                cwd=cwd,
                env=env,
                stdout=(
                    self._stdout_f
                    if self._stdout_f is not None
                    else subprocess.DEVNULL
                ),
                stderr=(
                    self._stderr_f
                    if self._stderr_f is not None
                    else subprocess.DEVNULL
                ),
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            self._close_log_files()
            self._transition(
                ProgramState.FATAL,
                message=f"spawn_oserror errno={exc.errno} {exc.strerror}",
                event_kind="fatal",
            )
            return self.status()
        self._proc = proc
        self._spawned_at = time.monotonic()
        self._transition(
            ProgramState.STARTING, message=f"spawned pid={proc.pid}",
            event_kind="spawned", pid=proc.pid,
        )
        self._spawn_threads()
        return self.status()

    def stop(self, *, timeout: float | None = None) -> ProgramStatus:
        """SIGTERM the subprocess; wait up to ``stopwaitsecs`` for clean
        exit; SIGKILL fallback if still alive.

        Tolerates :class:`PhantomProc` (hydrated from state file with
        no actual subprocess.Popen) by signalling the pid directly.
        """
        deadline = timeout if timeout is not None else self._config.stopwaitsecs
        proc = self._proc
        if proc is None:
            return self.status()
        self._stop_event.set()
        self._transition(
            ProgramState.STOPPING, message="stop requested",
            event_kind="stopped",
        )
        if proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, AttributeError):
                proc.send_signal(signal.SIGTERM)
        # PhantomProc has no .wait(); use os-level waitpid via os.waitpid
        # with WNOHANG so we don't block forever.
        try:
            proc.wait(timeout=deadline)  # type: ignore[attr-defined]
        except (subprocess.TimeoutExpired, AttributeError):
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
            with contextlib.suppress(subprocess.TimeoutExpired, AttributeError):
                proc.wait(timeout=2.0)  # type: ignore[attr-defined]
        self._join_threads(timeout=2.0)
        self._close_log_files()
        with self._state_lock():
            self._proc = None
            self._spawned_at = None
            self._last_exit_code = proc.poll()
        self._transition(
            ProgramState.STOPPED,
            message=f"stopped (exit_code={self._last_exit_code})",
            event_kind="stopped",
            exit_code=self._last_exit_code,
        )
        return self.status()

    def restart(self) -> ProgramStatus:
        """stop + start; returns post-start status."""
        self.stop()
        return self.start()

    def status(self) -> ProgramStatus:
        uptime = (
            time.monotonic() - self._spawned_at
            if self._spawned_at is not None
            else 0.0
        )
        pid = self._proc.pid if self._proc is not None else None
        return ProgramStatus(
            name=self._config.name,
            state=self._state,
            pid=pid,
            uptime_s=uptime,
            restart_count=self._restart_count,
            last_exit_code=self._last_exit_code,
            last_event=self._last_event,
            spawned_at=self._spawned_at,
        )

    def events(self, *, since: float | None = None) -> Iterator[ProgramEvent]:
        """Drain buffered events. ``since`` filters by ``ts >= since``."""
        drained: list[ProgramEvent] = []
        while True:
            try:
                drained.append(self._events.get_nowait())
            except queue.Empty:
                break
        for ev in drained:
            if since is None or ev.ts >= since:
                yield ev

    # ── 3 internal loops ──────────────────────────────────────────

    def _spawn_threads(self) -> None:
        with self._threads_lock:
            if self._threads:
                return
            self._stop_event.clear()
            self._readiness_tested.clear()
            self._threads = [
                threading.Thread(
                    target=self._waiter_loop,
                    name=f"sup-wait-{self._config.name}",
                    daemon=True,
                ),
                threading.Thread(
                    target=self._decider_loop,
                    name=f"sup-decide-{self._config.name}",
                    daemon=True,
                ),
                threading.Thread(
                    target=self._readiness_loop,
                    name=f"sup-ready-{self._config.name}",
                    daemon=True,
                ),
            ]
            for t in self._threads:
                t.start()

    def _waiter_loop(self) -> None:
        """Block on ``proc.wait()`` until the subprocess exits. Emits
        ``died`` event with exit code. One pass per spawned program.
        """
        proc = self._proc
        if proc is None:
            return
        try:
            rc = proc.wait()  # blocks; no busy-poll
        except Exception as exc:  # pragma: no cover — defensive
            self._emit(
                ProgramEvent(
                    ts=time.time(), kind="died", pid=proc.pid,
                    exit_code=-1, message=str(exc),
                )
            )
            return
        self._last_exit_code = rc
        self._emit(
            ProgramEvent(
                ts=time.time(), kind="died", pid=proc.pid, exit_code=rc,
                message="clean" if rc in _EXIT_CLEAN else "nonzero",
            )
        )

    def _readiness_loop(self) -> None:
        """Poll ``GET /health`` and advance STARTING → RUNNING when it
        succeeds. Sleeps on the state-change event (no busy-poll)
        between transitions.
        """
        while not self._stop_event.is_set():
            if self._state != ProgramState.STARTING:
                self._state_changed.wait(timeout=0.5)
                self._state_changed.clear()
                continue
            if self._probe_health():
                self._transition(
                    ProgramState.RUNNING,
                    message="readiness probe passed",
                    event_kind="ready",
                )
                continue
            time.sleep(self._READINESS_POLL_S)

    def _decider_loop(self) -> None:
        """Drain ``died`` events; call :func:`decide_restart`; apply
        the decision. Sleeps on ``queue.get`` between events.
        """
        while not self._stop_event.is_set():
            try:
                ev = self._events.get(timeout=0.5)
            except queue.Empty:
                continue
            if ev.kind != "died":
                continue
            decision = decide_restart(
                ev.exit_code if ev.exit_code is not None else -1,
                autorestart=self._config.autorestart,
                restart_count=self._restart_count,
                startretries=self._config.startretries,
                user_stopped=self._stop_event.is_set(),
            )
            self._apply_decision(ev, decision)

    def _apply_decision(
        self, died: ProgramEvent, decision: RestartDecision
    ) -> None:
        if decision.next_state == ProgramState.STOPPED:
            self._close_log_files()
            with self._state_lock():
                self._proc = None
                self._spawned_at = None
            self._transition(
                ProgramState.STOPPED, message=decision.reason,
                event_kind="stopped", exit_code=died.exit_code,
            )
            return
        if decision.next_state == ProgramState.FATAL:
            self._close_log_files()
            with self._state_lock():
                self._proc = None
            self._transition(
                ProgramState.FATAL, message=decision.reason,
                event_kind="fatal", exit_code=died.exit_code,
            )
            return
        # BACKOFF → wait → respawn.
        self._transition(
            ProgramState.BACKOFF, message=decision.reason,
            event_kind="backoff", exit_code=died.exit_code,
        )
        if self._sleep_with_stop(decision.backoff_s):
            return
        with self._state_lock():
            self._restart_count += 1
        self._emit(
            ProgramEvent(ts=time.time(), kind="restarted",
                         exit_code=died.exit_code)
        )
        self._respawn()

    def _respawn(self) -> None:
        """Re-Popen the program after a backoff. Same path as start()."""
        self._open_log_files()
        argv = self._config.argv()
        cwd = self._config.directory or None
        env = (
            {**os.environ, **self._config.environment}
            if self._config.environment
            else None
        )
        try:
            proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
                argv, cwd=cwd, env=env,
                stdout=self._stdout_f or subprocess.DEVNULL,
                stderr=self._stderr_f or subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            self._close_log_files()
            self._transition(
                ProgramState.FATAL,
                message=f"respawn_oserror errno={exc.errno}",
                event_kind="fatal",
            )
            return
        with self._state_lock():
            self._proc = proc
            self._spawned_at = time.monotonic()
        self._transition(
            ProgramState.STARTING, message=f"respawned pid={proc.pid}",
            event_kind="spawned", pid=proc.pid,
        )
        # New waiter for the new subprocess.
        threading.Thread(
            target=self._waiter_loop, daemon=True,
            name=f"sup-wait-{self._config.name}-{proc.pid}",
        ).start()

    # ── readiness probe ──────────────────────────────────────────

    def wait_ready(
        self, *, timeout: float | None = None
    ) -> bool:
        """Block until state becomes RUNNING or timeout elapses.

        Returns ``True`` iff the program became RUNNING within
        ``timeout`` (default = ``ProgramConfig.readiness_timeout``).
        Used by ``start()`` to give synchronous callers a readiness
        contract; the supervisor itself is async-driven.
        """
        deadline = time.monotonic() + (
            timeout if timeout is not None else self._config.readiness_timeout
        )
        event = self._state_changed
        while time.monotonic() < deadline:
            if self._state == ProgramState.RUNNING:
                return True
            if self._state in {
                ProgramState.STOPPED, ProgramState.FATAL, ProgramState.STOPPING,
            }:
                return False
            # Block on the state-change event; the readiness thread
            # will set it when /health answers ok. Fall back to a
            # small timeout so a missed signal doesn't deadlock.
            event.wait(timeout=min(0.5, max(0.05, deadline - time.monotonic())))
        return self._state == ProgramState.RUNNING

    def _probe_health(self) -> bool:
        port = self._config.port()
        if port is None:
            return False
        host = self._config.host()
        return health_body_ok(
            f"http://{host}:{port}/health", timeout=1.0
        )

    # ── helpers ───────────────────────────────────────────────────

    def _sleep_with_stop(self, secs: float) -> bool:
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if self._stop_event.is_set():
                return True
            time.sleep(min(0.1, end - time.monotonic()))
        return False

    def _join_threads(self, *, timeout: float) -> None:
        with self._threads_lock:
            threads = list(self._threads)
            self._threads = []
        for t in threads:
            t.join(timeout=timeout)

    def _transition(
        self,
        new: ProgramState,
        *,
        message: str,
        event_kind: str,
        pid: int | None = None,
        exit_code: int | None = None,
    ) -> None:
        with self._state_lock():
            self._state = new
            self._last_event = message
            # Snapshot for the cross-process state file.
            snapshot = ProgramStatus(
                name=self._config.name,
                state=new,
                pid=self._proc.pid if self._proc is not None else pid,
                uptime_s=(
                    time.monotonic() - self._spawned_at
                    if self._spawned_at is not None
                    else 0.0
                ),
                restart_count=self._restart_count,
                last_exit_code=exit_code,
                last_event=message,
                spawned_at=self._spawned_at,
            )
        # Persist AFTER releasing the lock to avoid holding it during
        # filesystem I/O.
        _write_state(self._config.name, snapshot)
        self._emit(
            ProgramEvent(
                ts=time.time(), kind=event_kind,
                pid=pid, exit_code=exit_code, message=message,
            )
        )
        self._state_changed.set()
        self._state_changed = threading.Event()  # reset for next waiter

    def _emit(self, ev: ProgramEvent) -> None:
        try:
            self._events.put_nowait(ev)
        except queue.Full:  # pragma: no cover — deque with no maxlen
            pass

    def _state_lock(self) -> threading.Lock:
        """Single mutex for the small mutable state. Status reads +
        a few field assignments are the critical sections; one lock
        keeps the model auditable.
        """
        return self._state_mutex

    def _open_log_files(self) -> None:
        if self._config.stdout_logfile:
            try:
                self._stdout_f = open(
                    self._config.stdout_logfile, "ab", buffering=0
                )
            except OSError:
                self._stdout_f = None
        if self._config.stderr_logfile:
            try:
                self._stderr_f = open(
                    self._config.stderr_logfile, "ab", buffering=0
                )
            except OSError:
                self._stderr_f = None

    def _close_log_files(self) -> None:
        for f in (self._stdout_f, self._stderr_f):
            if f is not None:
                with contextlib.suppress(OSError):
                    f.close()
        self._stdout_f = None
        self._stderr_f = None


__all__ = [
    "KernelSupervisor",
    "ProgramConfig",
    "ProgramEvent",
    "ProgramState",
    "ProgramStatus",
    "RestartDecision",
    "build_check_config_result",
    "build_command_error_result",
    "build_config_error_result",
    "build_events_result",
    "build_restart_result",
    "build_start_result",
    "build_status_result",
    "clear_state",
    "decide_restart",
    "default_program_config",
    "get_supervisor",
    "parse_program_config",
    "read_state_file",
    "status_from_state_file",
]
