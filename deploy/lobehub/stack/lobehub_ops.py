# ruff: noqa: S603, S607
"""LobeHub UI, patches, infra, and dev-server operations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from deploy.lobehub.stack.inspect import _infra_targets, _tcp_open
from deploy.lobehub.stack.process import (
    listening,
    pgrep_f,
    pid_alive,
    port_holder,
    read_pid,
    stop_pid,
    wait_for_port,
    write_pid,
)
from deploy.lobehub.stack.report import log
from deploy.lobehub.stack.session import StackSession


def sync_ui(session: StackSession) -> None:
    script = session.root / "scripts" / "sync_lobehub_ui.sh"
    env = {**os.environ, "LOBEHUB_RELEASE": session.config.lobehub.release}
    session.emit(log(f"sync lobehub-ui {session.config.lobehub.release}"))
    result = subprocess.run(
        [str(script)],
        cwd=session.root,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        session.emit(log("sync failed"))
        session.failed = True
        return
    apply_patches(session)


def ensure_ui(session: StackSession) -> None:
    ui = session.root / session.config.lobehub.dir
    pkg = ui / "package.json"
    expected = session.config.lobehub.release.lstrip("v")
    need = not pkg.is_file()
    if pkg.is_file():
        try:
            version = str(json.loads(pkg.read_text(encoding="utf-8")).get("version", ""))
        except json.JSONDecodeError:
            version = ""
        need = version != expected
    if need:
        session.emit(log(f"lobehub-ui version is not {expected}, syncing"))
        sync_ui(session)


def ensure_env(session: StackSession) -> None:
    ui = session.root / session.config.lobehub.dir
    dest = ui / ".env"
    template = session.root / session.config.lobehub.env_template
    if not dest.is_file() and template.is_file():
        session.emit(log(f"copy {template} → {dest}"))
        dest.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    if not dest.is_file():
        session.emit(log(f"warning: missing {dest}"))
        return
    _inject_gateway_env(dest, session.config.gateway.port, template)


def apply_patches(session: StackSession) -> None:
    ui = session.root / session.config.lobehub.dir
    if not (ui / "package.json").is_file():
        return
    session.emit(log("apply LCA patches"))
    from deploy.lobehub.engine import apply_patches as engine_apply

    engine_apply()


def ensure_infra(session: StackSession) -> None:
    if os.environ.get("LOBE_SKIP_INFRA") == "1":
        session.emit(log("skip docker infra (LOBE_SKIP_INFRA=1)"))
        return
    env_file = session.root / session.config.lobehub.dir / ".env"
    if not env_file.is_file():
        env_file = session.root / session.config.lobehub.env_template
    targets = _infra_targets(env_file) if env_file.is_file() else []
    ready = bool(targets) and all(_tcp_open(host, port) for _, host, port in targets)
    if ready and os.environ.get("LOBE_FORCE_INFRA") != "1":
        session.emit(log("reuse existing infra (postgres/redis/s3 reachable)"))
        return
    compose = session.root / session.config.lobehub.dir / "docker-compose" / "dev" / "docker-compose.yml"
    if not compose.is_file() or shutil.which("docker") is None:
        session.emit(log("skip docker infra (no compose or docker)"))
        return
    session.emit(log("start LobeHub infra (postgres + redis + rustfs)"))
    work = compose.parent
    if not (work / ".env").is_file() and (work / ".env.example").is_file():
        shutil.copy(work / ".env.example", work / ".env")
    subprocess.run(
        ["docker", "compose", "up", "-d", "postgresql", "redis", "rustfs", "rustfs-init"],
        cwd=work,
        check=False,
        capture_output=True,
        text=True,
    )


def start_dev(session: StackSession) -> None:
    ensure_ui(session)
    ensure_env(session)
    apply_patches(session)
    ui = session.root / session.config.lobehub.dir
    if not (ui / "node_modules").is_dir():
        session.emit(log("bun install"))
        subprocess.run(["bun", "install"], cwd=ui, check=False)
    if os.environ.get("LOBE_REUSE_DEV") == "1" and listening(session.config.lobehub.dev_port):
        session.emit(log(f"reuse LobeHub dev :{session.config.lobehub.dev_port}"))
        return
    stop_dev(session)
    if not wait_for_port(session.config.gateway.port, timeout_s=2.0):
        session.emit(log("gateway not ready before LobeHub dev"))
    env = _dev_env(session)
    log_path = session.root / session.config.lobehub.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    session.emit(log(f"start LobeHub {session.config.lobehub.release} :{session.config.lobehub.dev_port}"))
    handle = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        ["bun", "run", "dev"],
        cwd=ui,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    write_pid(session.root / session.config.lobehub.pid_file, proc.pid)
    if wait_for_port(session.config.lobehub.dev_port, timeout_s=120.0):
        session.emit(log(f"LobeHub dev ready pid={proc.pid}"))
        return
    session.emit(log(f"LobeHub dev start timeout — see {log_path}"))
    session.failed = True


def stop_dev(session: StackSession) -> None:
    ui = session.root / session.config.lobehub.dir
    pids = _dev_pids(session, ui)
    for pid in pids:
        session.emit(log(f"stop lobehub-dev pid {pid}"))
        stop_pid(pid)
    (session.root / session.config.lobehub.pid_file).unlink(missing_ok=True)
    lock = ui / ".next" / "dev" / "lock"
    lock.unlink(missing_ok=True)


def stop_vite(session: StackSession) -> None:
    ports = (
        session.config.lobehub.spa_port,
        session.config.lobehub.spa_mobile_port,
        session.config.lobehub.spa_auth_port,
    )
    pids: list[int] = []
    for port in ports:
        holder = port_holder(port)
        if holder is not None:
            pids.append(holder)
    ui = session.root / session.config.lobehub.dir
    pids.extend(pgrep_f(f"{ui}/node_modules/.bin/vite"))
    seen: set[int] = set()
    for pid in pids:
        if pid in seen or not pid_alive(pid):
            continue
        seen.add(pid)
        session.emit(log(f"stop vite pid {pid}"))
        stop_pid(pid)


def _dev_pids(session: StackSession, ui: Path) -> list[int]:
    pids: list[int] = []
    pid = read_pid(session.root / session.config.lobehub.pid_file)
    if pid is not None:
        pids.append(pid)
    lock = ui / ".next" / "dev" / "lock"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        lock_pid = data.get("pid")
        if isinstance(lock_pid, int):
            pids.append(lock_pid)
    holder = port_holder(session.config.lobehub.dev_port)
    if holder is not None:
        pids.append(holder)
    pids.extend(pgrep_f(f"{ui}/.*devStartupSequence"))
    pids.extend(pgrep_f(f"{ui}/.*next dev -p {session.config.lobehub.dev_port}"))
    unique: list[int] = []
    seen: set[int] = set()
    for item in pids:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _dev_env(session: StackSession) -> dict[str, str]:
    env = dict(os.environ)
    port = session.config.gateway.port
    env.setdefault("OPENAI_PROXY_URL", f"http://127.0.0.1:{port}/v1")
    env.setdefault("OPENAI_API_KEY", "lca-local")
    env.setdefault("ENABLED_OPENAI", "1")
    env["PORT"] = str(session.config.lobehub.dev_port)
    if not env.get("VITE_DEV_HOST"):
        from deploy.lobehub.stack.process import _lan_ip

        lan = os.environ.get("LOBE_LAN_IP") or _lan_ip()
        if lan and lan not in {"0.0.0.0", "127.0.0.1"}:  # noqa: S104
            env["VITE_DEV_HOST"] = lan
            session.emit(log(f"Vite SPA http://{lan}:{session.config.lobehub.spa_port}"))
    return env


def _inject_gateway_env(dest: Path, gateway_port: int, template: Path) -> None:
    gateway_url = f"http://127.0.0.1:{gateway_port}/v1"
    agent_config = "model=solo;provider=openai;chatConfig.searchMode=off"
    lines = dest.read_text(encoding="utf-8").splitlines()
    if template.is_file():
        existing_keys = {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}
        for line in template.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0]
            if key.startswith(("QWEN_", "OPENAI_", "DEFAULT_AGENT_CONFIG")) and key not in existing_keys:
                lines.append(line)
    values = {
        "OPENAI_PROXY_URL": gateway_url,
        "OPENAI_API_KEY": "lca-local",
        "QWEN_PROXY_URL": gateway_url,
        "QWEN_API_KEY": "lca-local",
        "ENABLED_QWEN": "0",
        "DEFAULT_AGENT_CONFIG": agent_config,
    }
    written = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.startswith("#"):
            key = line.split("=", 1)[0]
            if key in values:
                out.append(f"{key}={values[key]}")
                written.add(key)
                continue
        out.append(line)
    for key, value in values.items():
        if key not in written:
            out.append(f"{key}={value}")
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
