# ruff: noqa: S603
"""Mutating operations: gateway lifecycle, host provision, stack stop."""

from __future__ import annotations

import os
import subprocess
import time

from deploy.lobehub.stack import inspect as inspect_mod
from deploy.lobehub.stack.process import (
    pid_alive,
    port_holder,
    public_url,
    read_pid,
    stop_pid,
    wait_for_port,
    write_pid,
)
from deploy.lobehub.stack.report import log
from deploy.lobehub.stack.session import StackSession
from gateway.app import create_app


def snapshot_gateway(session: StackSession) -> None:
    session.previous = inspect_mod.process_snapshot(session.root, session.config)
    since = session.previous.started_epoch or 0.0
    session.newer = inspect_mod.newer_files(
        session.config.gateway.watch,
        since_epoch=since,
        glob=session.config.gateway.watch_glob,
        root=session.root,
    )
    reason = inspect_mod.restart_reason(
        force=session.command in {"restart-gateway", "restart"},
        previous=session.previous,
        newer=session.newer,
    )
    prev = session.previous
    session.emit(log(f"plan reason={reason} previous_pid={prev.pid or '—'} newer={len(session.newer)}"))
    for path in session.newer[:12]:
        try:
            rel = path.relative_to(session.root)
        except ValueError:
            rel = path
        session.emit(log(f"  newer {rel}"))


def inspect_gateway(session: StackSession) -> None:
    session.current = inspect_mod.process_snapshot(session.root, session.config)
    routes = inspect_mod.iter_app_routes(create_app())
    bound = inspect_mod.bind_surfaces(routes, session.config.surfaces)
    session.surfaces = inspect_mod.probe_surfaces(
        bound, session.config.surfaces, port=session.config.gateway.port
    )
    if session.command in {"restart-gateway", "gateway", "dev", "restart"} and not session.current.alive:
        session.failed = True


def start_gateway(session: StackSession, *, force: bool = False) -> None:
    snap = inspect_mod.process_snapshot(session.root, session.config)
    since = snap.started_epoch or 0.0
    newer = inspect_mod.newer_files(
        session.config.gateway.watch,
        since_epoch=since,
        glob=session.config.gateway.watch_glob,
        root=session.root,
    )
    if snap.alive and not force and not newer:
        session.emit(log(f"gateway already running (pid {snap.pid})"))
        return
    if snap.alive:
        session.emit(log(f"gateway code newer or forced — stopping pid {snap.pid}"))
        stop_gateway(session)
    _spawn_gateway(session)


def restart_gateway(session: StackSession) -> None:
    stop_gateway(session)
    _spawn_gateway(session)


def stop_gateway(session: StackSession) -> None:
    gw = session.config.gateway
    pid_path = session.root / gw.pid_file
    pid = read_pid(pid_path)
    if pid is not None and pid_alive(pid):
        session.emit(log(f"stop gateway pid {pid}"))
        stop_pid(pid)
    pid_path.unlink(missing_ok=True)
    holder = port_holder(gw.port)
    if holder is not None and pid_alive(holder):
        session.emit(log(f"release :{gw.port} holder pid {holder}"))
        stop_pid(holder)


def provision_host(session: StackSession) -> None:
    from lca.layer0_infra.host_runtime.config import HostRuntimeConfig
    from lca.layer0_infra.host_runtime.environment import HostEnvironment

    user = session.config.host.user
    session.emit(log(f"host provision {user}"))
    cfg = HostRuntimeConfig.from_yaml_or_default(session.root / session.config.host.config_file)
    ok = HostEnvironment(cfg).provision(user)
    if not ok:
        session.emit(log("warning: host provision reported failure"))


def inspect_host(session: StackSession) -> None:
    session.sections.extend(inspect_mod.inspect_host(session.root, session.config))


def inspect_patches(session: StackSession) -> None:
    ui = session.root / session.config.lobehub.dir
    session.sections.append(inspect_mod.inspect_patches(ui))


def inspect_lobehub(session: StackSession) -> None:
    session.sections.append(inspect_mod.inspect_lobehub(session.root, session.config))


def inspect_infra(session: StackSession) -> None:
    session.sections.append(inspect_mod.inspect_infra(session.root, session.config))


def start_infra(session: StackSession) -> None:
    from deploy.lobehub.stack.lobehub_ops import ensure_infra

    ensure_infra(session)


def start_lobehub_dev(session: StackSession) -> None:
    from deploy.lobehub.stack.lobehub_ops import start_dev

    start_dev(session)


def sync_lobehub(session: StackSession) -> None:
    from deploy.lobehub.stack.lobehub_ops import sync_ui

    sync_ui(session)


def stop_stack(session: StackSession) -> None:
    from deploy.lobehub.stack.lobehub_ops import stop_dev, stop_vite

    stop_dev(session)
    stop_vite(session)
    stop_gateway(session)


def _spawn_gateway(session: StackSession) -> None:
    gw = session.config.gateway
    run_dir = session.root / session.config.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = session.root / gw.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    url = public_url(gw.port)
    env = {**os.environ, "LCA_GATEWAY_PUBLIC_URL": url}
    cmd = [*gw.entry, "--host", gw.bind, "--port", str(gw.port)]
    session.emit(log(f"start gateway :{gw.port} public={url}"))
    handle = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=session.root,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    write_pid(session.root / gw.pid_file, proc.pid)
    if wait_for_port(gw.port, timeout_s=12.0):
        # Give /health a moment after the socket opens.
        for _ in range(16):
            snap = inspect_mod.process_snapshot(session.root, session.config)
            if snap.health is not None:
                session.emit(log(f"gateway ready pid={proc.pid} /health ok"))
                return
            time.sleep(0.25)
        session.emit(log(f"gateway port up pid={proc.pid} (health still warming)"))
        return
    session.emit(log(f"gateway start timeout — see {log_path}"))
    session.failed = True
    handle.close()
