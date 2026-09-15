"""``lca-ops kernel-supervisor`` — local supervisord-style process manager.

Commands (all support ``--json`` for agents):
- ``start``   — read supervisord-style config, spawn program + supervisor
- ``stop``    — SIGTERM + SIGKILL fallback after ``stopwaitsecs``
- ``restart`` — stop + start (atomic from caller's POV)
- ``status``  — program state, pid, uptime, restart count, last event
- ``events``  — drain buffered :class:`ProgramEvent` stream
- ``logs``   — ``tail -F`` the configured ``stdout_logfile`` /
                ``stderr_logfile``
- ``check-config <path>`` — parse and report errors without starting

Design
------
This is the dev-path replacement for system-level supervisors. The
production path is an external supervisor (ADR-0119). Here we keep
the LCA-internal abstraction small and supervisord-syntax-compatible
so operators can drop in a real ``supervisord`` later by pointing it
at the same ``[program:lca_kernel_dev]`` config file.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.services.kernel.supervisor import (
    KernelSupervisor,
    ProgramConfig,
    ProgramState,
    ProgramStatus,
    clear_state,
    default_program_config,
    parse_program_config,
    read_state_file,
)


def _program_status_json(s) -> dict[str, Any]:
    return {
        "name": s.name,
        "state": s.state.value,
        "pid": s.pid,
        "uptime_s": round(s.uptime_s, 2),
        "restart_count": s.restart_count,
        "last_exit_code": s.last_exit_code,
        "last_event": s.last_event,
        "spawned_at": s.spawned_at,
    }


def _program_event_json(e) -> dict[str, Any]:
    return {
        "ts": e.ts,
        "kind": e.kind,
        "pid": e.pid,
        "exit_code": e.exit_code,
        "message": e.message,
    }


def _find_orphan_pids() -> list[int]:
    """Return PIDs of running ``python -m lca_kernel serve`` procs.

    Used to refuse double-spawn when the kernel is already alive but
    not owned by *this* supervisor instance. We match on the **exact
    cmdline structure** (``/opt/lca/venv/bin/python`` + ``-m`` +
    ``lca_kernel`` + ``serve``) to avoid false positives from any
    shell whose argv happens to contain those substrings (e.g. a
    `ps | grep lca_kernel serve` filter).
    """
    import os as _os
    pids: list[int] = []
    for d in _os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        # cmdline uses NUL separators; tokens are split on NUL.
        tokens = raw.split(b"\x00")
        # Look for the canonical sequence anywhere in the cmdline:
        # any python* interpreter (path or name) + ``-m lca_kernel serve``.
        def _is_python(tok: bytes) -> bool:
            base = tok.split(b"/")[-1]  # /opt/lca/venv/bin/python3 → python3
            return base.startswith(b"python") and (
                base == b"python" or base[len(b"python"):][:1] in (b"", b".")
                or base[len(b"python"):][:1].isdigit()
            )
        for j in range(len(tokens) - 3):
            if (
                _is_python(tokens[j])
                and tokens[j + 1] == b"-m"
                and tokens[j + 2] == b"lca_kernel"
                and tokens[j + 3] == b"serve"
            ):
                try:
                    pids.append(int(d))
                except ValueError:
                    continue
                break
    return pids


def register(app: typer.Typer) -> None:
    """Register ``lca-ops kernel-supervisor {start,stop,restart,...}``."""

    @app.command(name="kernel-supervisor")
    def kernel_supervisor(
        action: str = typer.Argument(
            ...,
            help=(
                "One of: start, stop, restart, status, events, logs, "
                "check-config"
            ),
        ),
        config_path: Path | None = typer.Option(
            None,
            "--config",
            "-c",
            help="supervisord-style config file (default: dev-only config)",
        ),
        name: str = typer.Option(
            "lca_kernel_dev",
            "--name",
            help="Program name (for multi-program configs)",
        ),
        as_json: bool = typer.Option(
            False, "--json", help="Emit canonical JSON"
        ),
        tail_lines: int = typer.Option(
            50, "--lines",
            help="For `logs`: number of lines to print",
        ),
        follow: bool = typer.Option(
            False, "--follow", "-f",
            help="For `logs`: keep tailing (Ctrl+C to exit)",
        ),
        profile: str = typer.Option(
            "profiles/web-standard.yaml",
            "--profile",
            "-p",
            help="For dev-default config: profile path",
        ),
        port: int = typer.Option(
            8765, "--port",
            help="For dev-default config: HTTP port",
        ),
    ) -> None:
        """Local supervisord-style process manager for the LCA kernel.

        All subcommands accept ``--json`` for agent consumers. Output
        shape is :class:`dict` with these stable keys:

        - ``verdict``: ``"ready"`` / ``"failed"`` / ``"deferred"``
        - ``status``: :class:`ProgramStatus` snapshot (always present)
        - ``events``: list of recent :class:`ProgramEvent` (only on
          ``status`` / ``events`` actions)
        - ``reason``: human-readable one-liner (on failure)
        - ``next_command``: one ``lca-ops`` subcommand to run for
          diagnosis (on failure)
        """
        # ── check-config: standalone, no spawn ─────────────────────
        if action == "check-config":
            if config_path is None:
                _emit_error(
                    as_json,
                    "check-config requires --config <path>",
                    next_command="./scripts/lca-ops kernel-supervisor check-config --config <path>",
                )
                raise typer.Exit(2)
            try:
                progs = parse_program_config(config_path)
            except (ValueError, OSError) as exc:
                _emit_error(
                    as_json,
                    f"config invalid: {exc}",
                    next_command=f"./scripts/lca-ops kernel-supervisor check-config --config {config_path}",
                )
                raise typer.Exit(1) from None
            if as_json:
                typer.echo(
                    json.dumps(
                        {
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
                                for p in progs
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                typer.echo(f"OK {config_path}: {len(progs)} program(s)")
                for p in progs:
                    typer.echo(f"  - {p.name} port={p.port()} host={p.host()}")
            return

        # ── resolve config + build supervisor ──────────────────────
        cfg = _resolve_config(config_path, profile=profile, port=port)
        sup = _supervisor_singleton(cfg)

        # ── dispatch ──────────────────────────────────────────────
        if action == "start":
            # Refuse to double-spawn if a kernel is already alive.
            orphans = _find_orphan_pids()
            if orphans:
                _emit_error(
                    as_json,
                    f"kernel already running (pid={orphans}); refusing "
                    f"double-spawn. Run `./scripts/lca-ops kernel-supervisor "
                    f"stop` first or SIGTERM the orphan.",
                    status=_program_status_json(sup.status()),
                    next_command=(
                        f"./scripts/lca-ops kernel-supervisor stop --name {cfg.name}"
                    ),
                )
                raise typer.Exit(1)
            status = sup.start()
            ready = sup.wait_ready(timeout=cfg.readiness_timeout)
            status = sup.status()  # refresh after wait_ready
            if ready and status.state == ProgramState.RUNNING:
                _emit_ok(
                    as_json,
                    verdict="ready",
                    detail=(
                        f"supervisor started pid={status.pid} "
                        f"uptime={status.uptime_s:.1f}s"
                    ),
                    status=_program_status_json(status),
                    next_command=(
                        "./scripts/lca-ops kernel-supervisor status"
                        f" --name {cfg.name}"
                    ),
                )
                return
            _emit_error(
                as_json,
                f"supervisor start did not become ready within "
                f"{cfg.readiness_timeout}s: {status.last_event}",
                status=_program_status_json(status),
                next_command=(
                    f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
                ),
            )
            raise typer.Exit(1)

        if action == "stop":
            status = sup.stop()
            # Kill any orphan kernels not owned by this supervisor.
            orphans = _find_orphan_pids()
            for pid in orphans:
                import signal as _signal
                try:
                    os.kill(pid, _signal.SIGTERM)
                except OSError:
                    continue
            if orphans:
                import time as _time
                _time.sleep(min(cfg.stopwaitsecs, 5.0))
            _emit_ok(
                as_json,
                verdict="ready",
                detail=f"supervisor stopped (exit_code={status.last_exit_code}, orphans_killed={len(orphans)})",
                status=_program_status_json(status),
                next_command=(
                    f"./scripts/lca-ops kernel-supervisor start --name {cfg.name}"
                ),
            )
            return

        if action == "restart":
            status = sup.restart()
            ready = sup.wait_ready(timeout=cfg.readiness_timeout)
            status = sup.status()
            if ready:
                _emit_ok(
                    as_json,
                    verdict="ready",
                    detail=(
                        f"supervisor restarted pid={status.pid} "
                        f"restart_count={status.restart_count}"
                    ),
                    status=_program_status_json(status),
                    next_command=(
                        f"./scripts/lca-ops kernel-supervisor status --name {cfg.name}"
                    ),
                )
                return
            _emit_error(
                as_json,
                f"restart did not become ready within "
                f"{cfg.readiness_timeout}s: {status.last_event}",
                status=_program_status_json(status),
                next_command=f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}",
            )
            raise typer.Exit(1)

        if action == "status":
            status = sup.status()
            # If the in-process supervisor is empty (we never started
            # in this process), fall back to the persisted state file.
            if status.state == ProgramState.STOPPED and status.pid is None:
                persisted = _status_from_state_file(cfg)
                if persisted is not None:
                    status = persisted
            events = [_program_event_json(e) for e in sup.events()]
            verdict = (
                "ready" if status.state in {ProgramState.RUNNING, ProgramState.STOPPED}
                else "failed"
            )
            payload: dict[str, Any] = {
                "verdict": verdict,
                "status": _program_status_json(status),
                "events": events,
            }
            if status.state in {ProgramState.FATAL}:
                payload["next_command"] = (
                    f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
                )
            if as_json:
                typer.echo(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"{status.name}: state={status.state.value} "
                    f"pid={status.pid} uptime={status.uptime_s:.1f}s "
                    f"restarts={status.restart_count}"
                )
                if status.last_event:
                    typer.echo(f"  last_event: {status.last_event}")
                for ev in events[-5:]:
                    typer.echo(f"  {ev['kind']:10s} {ev['message'][:60]}")
            return

        if action == "events":
            events = [_program_event_json(e) for e in sup.events()]
            if as_json:
                typer.echo(json.dumps({"verdict": "ready", "events": events}, indent=2))
            else:
                for ev in events:
                    typer.echo(
                        f"{ev['ts']:.2f} {ev['kind']:10s} pid={ev['pid']} "
                        f"exit={ev['exit_code']} {ev['message'][:60]}"
                    )
            return

        if action == "logs":
            # Print tail of the configured stderr_logfile; supervise
            # ``--follow`` by polling the file mtime + size.
            log_path = cfg.stderr_logfile or cfg.stdout_logfile
            if log_path is None:
                _emit_error(
                    as_json,
                    "no stderr_logfile configured; set one in [program:...]",
                    next_command=f"edit {config_path} and add stderr_logfile=",
                )
                raise typer.Exit(2)
            _tail_log(Path(log_path), lines=tail_lines, follow=follow, as_json=as_json)
            return

        _emit_error(
            as_json,
            f"unknown action {action!r}",
            next_command="./scripts/lca-ops kernel-supervisor --help",
        )
        raise typer.Exit(2)


# ── helpers ─────────────────────────────────────────────────────────────


_SUPERVISORS: dict[str, KernelSupervisor] = {}


def _resolve_config(
    config_path: Path | None,
    *,
    profile: str,
    port: int,
) -> ProgramConfig:
    if config_path is None:
        return default_program_config(profile=profile, port=port)
    progs = parse_program_config(config_path)
    if len(progs) > 1:
        # Multi-program: caller picks by --name. Default = first.
        # (LCA dev path only needs one program.)
        return progs[0]
    return progs[0]


def _pid_alive(pid: int) -> bool:
    """True iff ``pid`` is a running process. ``os.kill(pid, 0)`` probes
    without sending a signal.
    """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _supervisor_singleton(cfg: ProgramConfig) -> KernelSupervisor:
    """One supervisor per CLI invocation. State persists across
    invocations via :func:`_read_state_file` (written by `_transition`
    in the previous process).
    """
    key = f"{cfg.name}:{cfg.directory}:{cfg.command}:{cfg.args}"
    sup = _SUPERVISORS.get(key)
    if sup is None:
        sup = KernelSupervisor(cfg)
        _SUPERVISORS[key] = sup
        # Hydrate from state file ONLY if the persisted pid is still
        # alive in /proc. Otherwise treat the program as STOPPED so
        # `start()` actually spawns a new one.
        st = read_state_file()
        if st is not None and st.get("program") == cfg.name:
            persisted_pid = st.get("pid")
            alive = (
                persisted_pid is not None and _pid_alive(int(persisted_pid))
            )
            if alive:
                sup._state = ProgramState(st["state"])
                sup._last_event = st.get("last_event", "")
                sup._restart_count = st.get("restart_count", 0)
                sup._last_exit_code = st.get("last_exit_code")
                sup._spawned_at = time.monotonic()  # restart the clock
                persisted_pid_int = int(persisted_pid)
                class _PhantomProc:
                    """Stand-in for :class:`subprocess.Popen` when the
                    supervisor was hydrated from a state file written
                    by a previous process. Forwards signals; the only
                    real subprocess work happens in a future ``start()``.
                    """
                    pid = persisted_pid_int
                    def poll(self) -> int | None:
                        try:
                            os.kill(persisted_pid_int, 0)
                        except OSError:
                            return -1
                        return None
                    def send_signal(self, sig: int) -> None:
                        with contextlib.suppress(ProcessLookupError):
                            os.kill(persisted_pid_int, sig)
                    def wait(self, timeout: float | None = None) -> int:
                        # PhantomProc can't really wait — block on the
                        # pid until it exits or timeout elapses.
                        deadline = time.monotonic() + (timeout or 10.0)
                        while time.monotonic() < deadline:
                            try:
                                waited_pid, status = os.waitpid(
                                    persisted_pid_int, os.WNOHANG
                                )
                                if waited_pid == persisted_pid_int:
                                    return os.waitstatus_to_exitcode(status)
                            except ChildProcessError:
                                return -1
                            time.sleep(0.1)
                        raise subprocess.TimeoutExpired(
                            "phantom", timeout
                        )
                sup._proc = _PhantomProc()
            else:
                # Persisted state refers to a dead pid; treat as
                # STOPPED so start() can spawn fresh.
                clear_state()
    return sup


def _status_from_state_file(cfg: ProgramConfig) -> ProgramStatus | None:
    """Read the persisted snapshot if the in-process supervisor is empty.

    Used by ``status`` and ``events`` when the supervisor was never
    ``start()``ed in this process — gives cross-process visibility.
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


def _emit_ok(
    as_json: bool, *, verdict: str, detail: str, status: dict[str, Any],
    next_command: str | None = None, events: list[dict[str, Any]] | None = None,
) -> None:
    payload: dict[str, Any] = {"verdict": verdict, "detail": detail, "status": status}
    if events is not None:
        payload["events"] = events
    if next_command is not None:
        payload["next_command"] = next_command
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"✅ {verdict}: {detail}")
        if next_command:
            typer.echo(f"   next: {next_command}")


def _emit_error(
    as_json: bool,
    reason: str,
    *,
    status: dict[str, Any] | None = None,
    next_command: str | None = None,
) -> None:
    payload: dict[str, Any] = {"verdict": "failed", "reason": reason}
    if status is not None:
        payload["status"] = status
    if next_command is not None:
        payload["next_command"] = next_command
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"❌ failed: {reason}", err=True)
        if next_command:
            typer.echo(f"   next: {next_command}", err=True)


def _tail_log(
    path: Path, *, lines: int, follow: bool, as_json: bool
) -> None:
    """Read last ``lines`` lines of ``path``; optionally follow."""
    if not path.exists():
        typer.echo(f"(no log file at {path})")
        return
    # Read tail
    try:
        data = path.read_bytes()
    except OSError as exc:
        typer.echo(f"(read error: {exc})", err=True)
        return
    text = data.decode("utf-8", errors="replace")
    buf = text.splitlines()[-lines:]
    if as_json:
        typer.echo(json.dumps({"verdict": "ready", "lines": buf}, indent=2))
        return
    sys.stdout.write("\n".join(buf) + "\n")
    if not follow:
        return
    # Follow: poll mtime + size.
    last_size = path.stat().st_size if path.exists() else 0
    try:
        while True:
            time.sleep(0.5)
            if not path.exists():
                continue
            cur = path.stat().st_size
            if cur > last_size:
                with path.open("rb") as fh:
                    fh.seek(last_size)
                    sys.stdout.write(
                        fh.read().decode("utf-8", errors="replace")
                    )
                    sys.stdout.flush()
                last_size = cur
    except KeyboardInterrupt:
        return


__all__ = ["register"]
