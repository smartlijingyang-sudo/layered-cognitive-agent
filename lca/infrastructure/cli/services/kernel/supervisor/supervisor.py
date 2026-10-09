"""``KernelSupervisor`` class and the per-process supervisor cache.

The spawner / waiter / decider loops and the readiness probe live here;
config parsing, state-file I/O, result builders and process helpers
live in sibling submodules (see the package ``__init__`` for the full
design).
"""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from typing import Any

from lca.infrastructure.cli.service.host_probing import health_body_ok
from lca.infrastructure.cli.services.kernel.supervisor.decisions import (
    _EXIT_CLEAN,
    decide_restart,
)
from lca.infrastructure.cli.services.kernel.supervisor.process import (
    _PhantomProc,
)
from lca.infrastructure.cli.services.kernel.supervisor.state import (
    _hydrate_from_state_file,
    _write_state,
)
from lca.infrastructure.cli.services.kernel.supervisor.types import (
    ProgramConfig,
    ProgramEvent,
    ProgramState,
    ProgramStatus,
    RestartDecision,
)

# Per-process cache of supervisor instances, keyed by config fingerprint.
# Lives in the service module so both ``kernel-supervisor`` and
# ``kernel-restart`` (CLI) reuse the same instance when invoked from
# the same Python process. Cross-process state is the JSON state file.
_SUPERVISOR_CACHE: dict[str, KernelSupervisor] = {}


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
        # _hydrate_from_state_file installs a _PhantomProc here when the
        # supervisor is rehydrated from a previous process' state file.
        self._proc: subprocess.Popen[bytes] | _PhantomProc | None = None
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

    def _build_subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._config.environment:
            env.update(self._config.environment)
        from lca.infrastructure.path import get_lca_home, get_real_user_home

        real_home = str(get_real_user_home())
        if ".agy-accounts" in env.get("HOME", ""):
            env["HOME"] = real_home
        env.setdefault("LCA_HOME", str(get_lca_home()))
        return env

    def start(self) -> ProgramStatus:
        """Spawn the subprocess; returns immediately. Three threads
        run until :meth:`stop` or FATAL.
        """
        if self._state in {ProgramState.RUNNING, ProgramState.STARTING}:
            return self.status()
        self._open_log_files()
        argv = self._config.argv()
        cwd = self._config.directory or None
        env = self._build_subprocess_env()
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=(self._stdout_f if self._stdout_f is not None else subprocess.DEVNULL),
                stderr=(self._stderr_f if self._stderr_f is not None else subprocess.DEVNULL),
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
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
            ProgramState.STARTING,
            message=f"spawned pid={proc.pid}",
            event_kind="spawned",
            pid=proc.pid,
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
            ProgramState.STOPPING,
            message="stop requested",
            event_kind="stopped",
        )
        if proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, AttributeError):
                proc.send_signal(signal.SIGTERM)
        # Both union members expose .wait() (Popen and _PhantomProc).
        try:
            proc.wait(timeout=deadline)
        except (subprocess.TimeoutExpired, AttributeError):
            with contextlib.suppress(OSError, ProcessLookupError):
                # already dead or reaped: SIGKILL has nothing to signal
                os.kill(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired, AttributeError):
                proc.wait(timeout=2.0)
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
        uptime = time.monotonic() - self._spawned_at if self._spawned_at is not None else 0.0
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
                    ts=time.time(),
                    kind="died",
                    pid=proc.pid,
                    exit_code=-1,
                    message=str(exc),
                )
            )
            return
        self._last_exit_code = rc
        self._emit(
            ProgramEvent(
                ts=time.time(),
                kind="died",
                pid=proc.pid,
                exit_code=rc,
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

    def _apply_decision(self, died: ProgramEvent, decision: RestartDecision) -> None:
        if decision.next_state == ProgramState.STOPPED:
            self._close_log_files()
            with self._state_lock():
                self._proc = None
                self._spawned_at = None
            self._transition(
                ProgramState.STOPPED,
                message=decision.reason,
                event_kind="stopped",
                exit_code=died.exit_code,
            )
            return
        if decision.next_state == ProgramState.FATAL:
            self._close_log_files()
            with self._state_lock():
                self._proc = None
            self._transition(
                ProgramState.FATAL,
                message=decision.reason,
                event_kind="fatal",
                exit_code=died.exit_code,
            )
            return
        # BACKOFF → wait → respawn.
        self._transition(
            ProgramState.BACKOFF,
            message=decision.reason,
            event_kind="backoff",
            exit_code=died.exit_code,
        )
        if self._sleep_with_stop(decision.backoff_s):
            return
        with self._state_lock():
            self._restart_count += 1
        self._emit(ProgramEvent(ts=time.time(), kind="restarted", exit_code=died.exit_code))
        self._respawn()

    def _respawn(self) -> None:
        """Re-Popen the program after a backoff. Same path as start()."""
        self._open_log_files()
        argv = self._config.argv()
        cwd = self._config.directory or None
        env = self._build_subprocess_env()
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
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
            ProgramState.STARTING,
            message=f"respawned pid={proc.pid}",
            event_kind="spawned",
            pid=proc.pid,
        )
        # New waiter for the new subprocess.
        threading.Thread(
            target=self._waiter_loop,
            daemon=True,
            name=f"sup-wait-{self._config.name}-{proc.pid}",
        ).start()

    # ── readiness probe ──────────────────────────────────────────

    def wait_ready(self, *, timeout: float | None = None) -> bool:
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
                ProgramState.STOPPED,
                ProgramState.FATAL,
                ProgramState.STOPPING,
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
        return health_body_ok(f"http://{host}:{port}/health", timeout=1.0)

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
                    time.monotonic() - self._spawned_at if self._spawned_at is not None else 0.0
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
                ts=time.time(),
                kind=event_kind,
                pid=pid,
                exit_code=exit_code,
                message=message,
            )
        )
        self._state_changed.set()
        self._state_changed = threading.Event()  # reset for next waiter

    def _emit(self, ev: ProgramEvent) -> None:
        # ``queue.Queue()`` is constructed with the default ``maxsize=0``, i.e.
        # unbounded, so ``put_nowait`` cannot raise ``queue.Full``.
        self._events.put_nowait(ev)

    def _state_lock(self) -> threading.Lock:
        """Single mutex for the small mutable state. Status reads +
        a few field assignments are the critical sections; one lock
        keeps the model auditable.
        """
        return self._state_mutex

    def _open_log_files(self) -> None:
        if self._config.stdout_logfile:
            try:
                # The handle must outlive the function: the subprocess
                # inherits it and we want every kernel stdout byte flushed
                # through it until the supervisor's stop()/close cycle.
                self._stdout_f = open(  # noqa: SIM115
                    self._config.stdout_logfile, "ab", buffering=0
                )
            except OSError:
                self._stdout_f = None
        if self._config.stderr_logfile:
            try:
                # Same rationale as _stdout_f above.
                self._stderr_f = open(  # noqa: SIM115
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
