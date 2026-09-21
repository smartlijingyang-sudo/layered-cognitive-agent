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

This module is a thin dispatcher: action payload shapes live in
:mod:`lca.infrastructure.cli.services.kernel.supervisor` (the
``build_*_result`` builders) so both ``lca-ops kernel-supervisor
{start,stop,...}`` and ``lca-ops kernel-restart`` share one
wire contract. ``_render`` below is the single output function; it
takes the dict the builder produced and emits JSON or human text
depending on ``--json``.
"""

from __future__ import annotations

import contextlib
import json
import os
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
    build_check_config_result,
    build_command_error_result,
    build_config_error_result,
    build_events_result,
    build_restart_result,
    build_start_result,
    build_status_result,
    build_stop_result,
    default_program_config,
    get_supervisor,
    parse_program_config,
    status_from_state_file,
)

# ── Output rendering ──────────────────────────────────────────────────


def _render(payload: dict[str, Any], *, json_mode: bool) -> dict[str, Any]:
    """Single output function for every action result.

    JSON mode: ``typer.echo(json.dumps(payload, indent=2))``.
    Text mode: short verdict + next hint line, ``next_command``
    goes to stderr so it doesn't pollute stdout pipelines.

    Returns the dict for callers that want to inspect the result
    programmatically (e.g. tests).
    """
    if json_mode:
        typer.echo(json.dumps(payload, indent=2))
        return payload

    verdict = payload.get("verdict", "?")
    detail = payload.get("detail") or payload.get("reason", "")
    marker = "✅" if verdict == "ready" else "❌"
    typer.echo(f"{marker} {verdict}: {detail}")
    next_cmd = payload.get("next_command")
    if next_cmd:
        typer.echo(f"   next: {next_cmd}", err=True)
    return payload


# ── CLI-side helpers ──────────────────────────────────────────────────


def _find_orphan_pids() -> list[int]:
    """Return PIDs of running ``python -m lca_kernel serve`` procs.

    Used to refuse double-spawn when the kernel is already alive but
    not owned by *this* supervisor instance. We match on the **exact
    cmdline structure** to avoid false positives from any shell whose
    argv happens to contain those substrings.
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
        tokens = raw.split(b"\x00")

        def _is_python(tok: bytes) -> bool:
            base = tok.split(b"/")[-1]
            return base.startswith(b"python") and (
                base == b"python"
                or base[len(b"python"):][:1] in (b"", b".")
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


def _resolve_config(
    config_path: Path | None, *, profile: str, port: int
) -> ProgramConfig:
    if config_path is None:
        return default_program_config(profile=profile, port=port)
    progs = parse_program_config(config_path)
    if not progs:
        raise ValueError(f"{config_path}: no [program:...] sections found")
    return progs[0]


def _tail_log(
    path: Path, *, lines: int, follow: bool, json_mode: bool
) -> None:
    """Read last ``lines`` lines of ``path``; optionally follow."""
    if not path.exists():
        typer.echo(f"(no log file at {path})")
        return
    try:
        data = path.read_bytes()
    except OSError as exc:
        typer.echo(f"(read error: {exc})", err=True)
        return
    text = data.decode("utf-8", errors="replace")
    buf = text.splitlines()[-lines:]
    if json_mode:
        typer.echo(json.dumps({"verdict": "ready", "lines": buf}, indent=2))
        return
    sys.stdout.write("\n".join(buf) + "\n")
    if not follow:
        return
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


def _kill_orphans(pids: list[int], grace_s: float) -> None:
    """SIGTERM each orphan, wait up to ``grace_s``, return."""
    import signal as _signal

    for pid in pids:
        with contextlib.suppress(OSError):
            os.kill(pid, _signal.SIGTERM)
    if pids:
        time.sleep(min(grace_s, 5.0))


# ── Dispatcher ────────────────────────────────────────────────────────


def register(app: typer.Typer) -> None:
    """Register ``lca-ops kernel-supervisor {start,stop,restart,...}``.

    The dispatcher is intentionally thin: every action's payload shape
    lives in the service layer (see ``build_*_result``); this function
    only does:

    1. Parse typer args + resolve config.
    2. Look up the (shared) supervisor instance via :func:`get_supervisor`.
    3. Run the action.
    4. Build a payload via ``build_*_result``.
    5. ``_render`` to stdout (json) / stderr (text).
    """

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
            None, "--config", "-c",
            help="supervisord-style config file (default: dev-only config)",
        ),
        name: str = typer.Option(
            "lca_kernel_dev", "--name",
            help="Program name (for multi-program configs)",
        ),
        as_json: bool = typer.Option(
            False, "--json", help="Emit canonical JSON"
        ),
        tail_lines: int = typer.Option(
            50, "--lines", help="For `logs`: number of lines to print",
        ),
        follow: bool = typer.Option(
            False, "--follow", "-f",
            help="For `logs`: keep tailing (Ctrl+C to exit)",
        ),
        profile: str = typer.Option(
            "profiles/web-assistant.yaml", "--profile", "-p",
            help="For dev-default config: profile path",
        ),
        port: int = typer.Option(
            8765, "--port",
            help="For dev-default config: HTTP port",
        ),
    ) -> None:
        """Local supervisord-style process manager for the LCA kernel.

        Output shape (--json): ``{verdict, detail|reason, status,
        next_command?, events?}``. Text mode prints verdict + next
        hint to stderr.
        """
        # ── check-config: standalone, no spawn ─────────────────────
        if action == "check-config":
            if config_path is None:
                _render(
                    {
                        "verdict": "failed",
                        "reason": "check-config requires --config <path>",
                        "next_command": (
                            "./scripts/lca-ops kernel-supervisor "
                            "check-config --config <path>"
                        ),
                    },
                    json_mode=as_json,
                )
                raise typer.Exit(2) from None
            try:
                progs = parse_program_config(config_path)
            except (ValueError, OSError) as exc:
                _render(
                    build_config_error_result(config_path, exc),
                    json_mode=as_json,
                )
                raise typer.Exit(1) from None
            _render(
                build_check_config_result(config_path, progs),
                json_mode=as_json,
            )
            return

        # ── resolve config + supervisor (shared across CLI calls) ──
        try:
            cfg = _resolve_config(config_path, profile=profile, port=port)
        except (ValueError, OSError) as exc:
            _render(
                build_config_error_result(
                    config_path or "(default)", exc,
                ),
                json_mode=as_json,
            )
            raise typer.Exit(2) from None
        sup = get_supervisor(cfg)

        # ── dispatch ──────────────────────────────────────────────
        if action == "start":
            orphans = _find_orphan_pids()
            if orphans:
                _render(
                    build_command_error_result(
                        action, cfg,
                        orphan_pids=orphans,
                        status=sup.status(),
                    ),
                    json_mode=as_json,
                )
                raise typer.Exit(1) from None
            sup.start()
            ready = sup.wait_ready(timeout=cfg.readiness_timeout)
            status = sup.status()
            _render(
                build_start_result(cfg, status, ready=ready),
                json_mode=as_json,
            )
            if not ready:
                raise typer.Exit(1) from None
            return

        if action == "stop":
            status = sup.stop()
            orphans = _find_orphan_pids()
            _kill_orphans(orphans, grace_s=cfg.stopwaitsecs)
            status = sup.status()
            _render(
                build_stop_result(cfg, status, orphans_killed=len(orphans)),
                json_mode=as_json,
            )
            return

        if action == "restart":
            sup.restart()
            ready = sup.wait_ready(timeout=cfg.readiness_timeout)
            status = sup.status()
            _render(
                build_restart_result(cfg, status, ready=ready),
                json_mode=as_json,
            )
            if not ready:
                raise typer.Exit(1) from None
            return

        if action == "status":
            status = _status_with_hydration(sup, cfg)
            _render(
                build_status_result(
                    cfg,
                    status,
                    events=list(sup.events()),
                    is_fatal=(status.state == ProgramState.FATAL),
                ),
                json_mode=as_json,
            )
            return

        if action == "events":
            _render(
                build_events_result(list(sup.events())),
                json_mode=as_json,
            )
            return

        if action == "logs":
            log_path = cfg.stderr_logfile or cfg.stdout_logfile
            if log_path is None:
                _render(
                    {
                        "verdict": "failed",
                        "reason": "no stderr_logfile configured",
                        "next_command": (
                            f"edit {config_path or '<default>'} and add "
                            "stderr_logfile="
                        ),
                    },
                    json_mode=as_json,
                )
                raise typer.Exit(2) from None
            _tail_log(
                Path(log_path), lines=tail_lines, follow=follow,
                json_mode=as_json,
            )
            return

        _render(
            build_command_error_result(action, cfg),
            json_mode=as_json,
        )
        raise typer.Exit(2) from None


# ── Status hydration ──────────────────────────────────────────────────


def _status_with_hydration(
    sup: KernelSupervisor, cfg: ProgramConfig
) -> ProgramStatus:
    """If the in-process supervisor is empty (state=STOPPED + pid=None),
    fall back to the persisted state file. Returns the most informative
    :class:`ProgramStatus` snapshot for this process.
    """
    status = sup.status()
    if status.state == ProgramState.STOPPED and status.pid is None:
        persisted = status_from_state_file(cfg)
        if persisted is not None:
            return persisted
    return status


__all__ = ["register"]
