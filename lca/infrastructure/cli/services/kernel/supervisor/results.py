"""Action result builders (wire contract) for the kernel supervisor.

Every action (start, stop, restart, status, events, logs, check-config)
returns the same shape — a dict with verdict / detail / status / events
/ next_command keys. Builders live here so service-layer tests can pin
the wire contract without touching the CLI dispatcher.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.infrastructure.cli.services.kernel.supervisor.types import (
    ProgramConfig,
    ProgramState,
    ProgramStatus,
)


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
    cfg: ProgramConfig,
    status: ProgramStatus,
    *,
    ready: bool,
) -> dict[str, Any]:
    """Result of ``start`` action.

    ``ready=True`` → verdict=ready, next_command points to status.
    ``ready=False`` → verdict=failed, next_command points to logs.
    """
    if ready:
        return {
            "verdict": "ready",
            "detail": (f"supervisor started pid={status.pid} uptime={status.uptime_s:.1f}s"),
            "status": _status_dict(status),
            "next_command": (f"./scripts/lca-ops kernel-supervisor status --name {cfg.name}"),
        }
    return {
        "verdict": "failed",
        "detail": (
            f"supervisor start did not become ready within "
            f"{cfg.readiness_timeout}s: {status.last_event}"
        ),
        "status": _status_dict(status),
        "next_command": (f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"),
    }


def build_stop_result(
    cfg: ProgramConfig,
    status: ProgramStatus,
    *,
    orphans_killed: int,
) -> dict[str, Any]:
    return {
        "verdict": "ready",
        "detail": (
            f"supervisor stopped (exit_code={status.last_exit_code}, "
            f"orphans_killed={orphans_killed})"
        ),
        "status": _status_dict(status),
        "next_command": (f"./scripts/lca-ops kernel-supervisor start --name {cfg.name}"),
    }


def build_restart_result(
    cfg: ProgramConfig,
    status: ProgramStatus,
    *,
    ready: bool,
) -> dict[str, Any]:
    if ready:
        return {
            "verdict": "ready",
            "detail": (
                f"LCA kernel restarted (pid={status.pid}, restart_count={status.restart_count})"
            ),
            "status": _status_dict(status),
            "next_command": (f"./scripts/lca-ops kernel-supervisor status --name {cfg.name}"),
        }
    return {
        "verdict": "failed",
        "detail": (
            f"restart did not become ready within {cfg.readiness_timeout}s: {status.last_event}"
        ),
        "status": _status_dict(status),
        "next_command": (f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"),
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
        payload["next_command"] = f"./scripts/lca-ops kernel-supervisor logs --name {cfg.name}"
    return payload


def build_events_result(events) -> dict[str, Any]:
    return {"verdict": "ready", "events": _events_dict(events)}


def build_check_config_result(
    config_path: str | Path,
    programs: list[ProgramConfig],
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
    config_path: str | Path,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "verdict": "failed",
        "reason": f"config invalid: {exc}",
        "next_command": (
            f"./scripts/lca-ops kernel-supervisor check-config --config {config_path}"
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
            "next_command": (f"./scripts/lca-ops kernel-supervisor stop --name {cfg.name}"),
        }
    return {
        "verdict": "failed",
        "reason": f"unknown action {action!r}",
        "next_command": "./scripts/lca-ops kernel-supervisor --help",
    }
