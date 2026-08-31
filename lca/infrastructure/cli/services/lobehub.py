"""LobeHub service — Next.js frontend.

Full lifecycle: sync source, apply patches, configure env, install deps,
start dev server, stop, restart.

Design: each phase is a separate method, all idempotent. The service
tracks what's been done via stamps so restart doesn't redo setup.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lca.infrastructure.cli.config import GatewayConfig, LobeHubConfig
from lca.infrastructure.cli.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    free_port,
    http_ready,
    kill_tree,
    pid_alive,
    pid_on_port,
)
from lca.infrastructure.cli.state import StateStore


class LobeHubService:
    """LobeHub Next.js frontend.

    Next on ``dev_port`` is the service. Vite SPA on ``spa_port`` is a
    sidecar with an independent lifetime — its exit must not kill Next.
    """

    _SPA_NAME = "lobehub-spa"

    def __init__(
        self,
        config: LobeHubConfig,
        gateway: GatewayConfig,
        state_dir: Path,
        root: Path,
    ) -> None:
        self.name = "lobehub"
        self._config = config
        self._gateway = gateway
        self._state = StateStore(state_dir)
        self._root = root
        self._dir = root / config.dir

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Start Next (the service) and the Vite sidecar if missing."""
        current = self.state()
        if current.is_running:
            return current

        self.ensure_ready()
        pid = self._ensure_next()
        if pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="spawn failed")
        if not self._next_ready():
            return ServiceState(
                status=ServiceStatus.STOPPED,
                pid=pid,
                detail="dev server start timeout",
            )
        self._ensure_spa()
        return ServiceState(
            status=ServiceStatus.RUNNING,
            pid=pid,
            port=self._config.dev_port,
            detail="dev server ready",
        )

    def stop(self) -> ServiceState:
        """Stop Next and the Vite sidecar."""
        pids = self._collect_pids()
        for pid in pids:
            kill_tree(pid)

        time.sleep(0.5)
        free_port(self._config.dev_port)
        free_port(self._config.spa_port)
        self._state.remove_pid(self.name)
        self._state.remove_pid(self._SPA_NAME)

        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        """Restart the dev server."""
        self.stop()
        return self.start()

    # ── Setup (idempotent) ────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Ensure all prerequisites: source, patches, env, deps.

        Each step checks if it needs to run, so this is safe to call
        repeatedly.
        """
        worked = False
        worked |= self._ensure_source()
        worked |= self._ensure_patches()
        worked |= self._ensure_env()
        worked |= self._ensure_deps()
        return worked

    # ── Health ────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Observe current state."""
        stored_pid = self._state.read_pid(self.name)
        checks: list[HealthCheck] = []

        # Dev server responding? HTTP is the ground truth for "UI is up".
        dev_ok = http_ready(f"{self._config.dev_url}/", timeout=2.0)
        checks.append(HealthCheck("dev", dev_ok, f":{self._config.dev_port}"))

        spa_pid = pid_on_port(self._config.spa_port)
        spa_ok = spa_pid is not None
        stored_spa = self._state.read_pid(self._SPA_NAME)
        if spa_ok and spa_pid and (stored_spa is None or not pid_alive(stored_spa)):
            self._state.write_pid(self._SPA_NAME, spa_pid)
        checks.append(HealthCheck("spa", spa_ok, f":{self._config.spa_port}" if spa_ok else "none"))

        # Reconcile PID: next-server may outlive the recorded bun parent.
        port_pid = pid_on_port(self._config.dev_port) if dev_ok else None
        if dev_ok and port_pid and (stored_pid is None or not pid_alive(stored_pid)):
            self._state.write_pid(self.name, port_pid)

        pid = stored_pid if stored_pid and pid_alive(stored_pid) else port_pid
        process_ok = pid is not None and pid_alive(pid)
        checks.append(HealthCheck("process", process_ok, f"pid={pid}" if pid else "none"))

        # Source synced?
        source_ok = self._dir.exists() and (self._dir / "package.json").exists()
        checks.append(HealthCheck("source", source_ok, str(self._dir)))

        # Patches applied?
        deploy_dir = self._root / "deploy" / "lobehub"
        patches_ok = (self._dir / ".lca-patched").exists()
        patch_count = self._count_patches(deploy_dir)
        patch_drift = self._state.detect_changes("patches", [deploy_dir], "*")
        if not patches_ok:
            patch_detail = f"{patch_count} patches, NOT applied"
        elif patch_drift.has_changes:
            patch_detail = f"{patch_count} patches, stale ({patch_drift.summary})"
        else:
            patch_detail = f"{patch_count} patches, up-to-date"
        checks.append(
            HealthCheck("patches", patches_ok and not patch_drift.has_changes, patch_detail)
        )

        why = ""
        next_action = ""
        patches_stale = patches_ok and patch_drift.has_changes
        patches_missing = not patches_ok
        if dev_ok and not spa_ok:
            status = ServiceStatus.DEGRADED
            detail = "Next up, Vite sidecar down"
            why = (
                f"SPA sidecar :{self._config.spa_port} is down; "
                f"{self._config.dev_url} still answers"
            )
            next_action = "./scripts/lca-ops lobehub heal"
        elif dev_ok:
            status = ServiceStatus.RUNNING
            detail = "healthy"
            if patches_stale or patches_missing:
                detail = f"healthy (patches need reapply — {patch_detail})"
                why = "patch source changed since last apply"
                next_action = "./scripts/lca-ops lobehub ensure"
        elif process_ok:
            status = ServiceStatus.DEGRADED
            detail = "process alive but dev server not responding"
            why = f"{self._config.dev_url} is not answering yet"
            next_action = "./scripts/lca-ops logs lobehub"
        elif not source_ok:
            status = ServiceStatus.STOPPED
            detail = "source missing"
            why = f"{self._dir} has no package.json — UI is not synced"
            next_action = "./scripts/lca-ops lobehub ensure"
        else:
            status = ServiceStatus.STOPPED
            detail = "not running"
            why = f"UI is down — open {self._config.dev_url} will fail"
            next_action = "./scripts/lca-ops lobehub start"

        return ServiceState(
            status=status,
            checks=tuple(checks),
            pid=pid if process_ok else None,
            port=self._config.dev_port,
            detail=detail,
            why=why,
            next_action=next_action,
        )

    def heal(self) -> ServiceState:
        """Repair without a death pact: Next stays up if only the sidecar is missing."""
        current = self.state()
        if current.is_running and not current.next_action:
            return current

        spa_down = not any(c.name == "spa" and c.ok for c in current.checks)
        next_up = any(c.name == "dev" and c.ok for c in current.checks)

        if next_up and spa_down and current.next_action.endswith("heal"):
            self._ensure_spa()
            return self.state()

        if current.is_running:
            self.stop()

        self.ensure_ready()
        return self.start()

    # ── Setup Internals ───────────────────────────────────────────────

    def _ensure_source(self) -> bool:
        """Sync LobeHub source if not present or version mismatch."""
        pkg = self._dir / "package.json"
        if pkg.exists():
            content = pkg.read_text()
            if f'"version": "{self._config.release.lstrip("v")}"' in content:
                return False

        # Run sync script
        sync_script = self._root / "scripts" / "sync_lobehub_ui.sh"
        if not sync_script.exists():
            return False

        try:
            subprocess.run(  # noqa: S603
                ["bash", str(sync_script)],  # noqa: S607
                env={"LOBEHUB_RELEASE": self._config.release},
                cwd=self._root,
                capture_output=True,
                timeout=300,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _count_patches(deploy_dir: Path) -> int:
        """Count patch module files (excluding __init__ and __pycache__)."""
        patches_dir = deploy_dir / "patches"
        if not patches_dir.is_dir():
            return 0
        return sum(
            1
            for f in patches_dir.rglob("*.py")
            if f.name != "__init__.py" and "__pycache__" not in f.parts
        )

    def _ensure_patches(self) -> bool:
        """Apply patches if source changed."""
        # Check if patches need reapplication
        deploy_dir = self._root / "deploy" / "lobehub"
        if not self._state.has_changed("patches", [deploy_dir], "*"):
            return False

        # Apply patches
        patch_script = self._root / "deploy" / "lobehub" / "patch_lobehub.py"
        if not patch_script.exists():
            return False

        try:
            subprocess.run(  # noqa: S603
                ["python3", str(patch_script)],  # noqa: S607
                cwd=self._root,
                capture_output=True,
                timeout=60,
            )
            self._state.save_snapshot("patches", [deploy_dir], "*")
            return True
        except Exception:
            return False

    def _ensure_env(self) -> bool:
        """Configure .env for LobeHub."""
        env_file = self._dir / ".env"
        template = self._root / self._config.env_template

        if not template.exists():
            return False

        # Copy template if .env doesn't exist
        if not env_file.exists():
            env_file.write_text(template.read_text())

        # Update gateway proxy URLs
        gateway_url = f"{self._gateway.base_url}/v1"
        lines = env_file.read_text().splitlines()
        updated = []
        changed = False

        for line in lines:
            if line.startswith("OPENAI_PROXY_URL="):
                updated.append(f"OPENAI_PROXY_URL={gateway_url}")
                changed = True
            elif line.startswith("OPENAI_API_KEY="):
                updated.append("OPENAI_API_KEY=lca-local")
                changed = True
            elif line.startswith("QWEN_PROXY_URL="):
                updated.append(f"QWEN_PROXY_URL={gateway_url}")
                changed = True
            elif line.startswith("QWEN_API_KEY="):
                updated.append("QWEN_API_KEY=lca-local")
                changed = True
            else:
                updated.append(line)

        if changed:
            env_file.write_text("\n".join(updated) + "\n")

        return changed

    def _ensure_deps(self) -> bool:
        """Install dependencies if node_modules missing."""
        if (self._dir / "node_modules").exists():
            return False

        try:
            subprocess.run(
                ["bun", "install"],  # noqa: S607
                cwd=self._dir,
                capture_output=True,
                timeout=300,
            )
            return True
        except Exception:
            return False

    # ── Lifecycle Internals ───────────────────────────────────────────

    def _next_ready(self) -> bool:
        needed = 3
        consec = 0
        for _ in range(120):
            time.sleep(0.5)
            if http_ready(f"{self._config.dev_url}/", timeout=1.0):
                consec += 1
                if consec >= needed:
                    return True
            else:
                consec = 0
        return False

    def _spa_listening(self) -> bool:
        return pid_on_port(self._config.spa_port) is not None

    def _ensure_next(self) -> int | None:
        if http_ready(f"{self._config.dev_url}/", timeout=1.0):
            port_pid = pid_on_port(self._config.dev_port)
            if port_pid:
                self._state.write_pid(self.name, port_pid)
                return port_pid
            stored = self._state.read_pid(self.name)
            if stored and pid_alive(stored):
                return stored
        pid = self._spawn_script("dev:next", self.name)
        if pid is not None:
            self._state.write_pid(self.name, pid)
        return pid

    def _ensure_spa(self) -> int | None:
        if self._spa_listening():
            port_pid = pid_on_port(self._config.spa_port)
            if port_pid:
                self._state.write_pid(self._SPA_NAME, port_pid)
                return port_pid
        pid = self._spawn_script("dev:spa", self._SPA_NAME)
        if pid is not None:
            self._state.write_pid(self._SPA_NAME, pid)
        return pid

    def _child_env(self) -> dict[str, str]:
        import os

        return {
            **os.environ,
            "PORT": str(self._config.dev_port),
            "SPA_PORT": str(self._config.spa_port),
            "VITE_DEV_PORT": str(self._config.spa_port),
            "OPENAI_PROXY_URL": f"{self._gateway.base_url}/v1",
            "OPENAI_API_KEY": "lca-local",
            "ENABLED_OPENAI": "1",
        }

    def _spawn_script(self, script: str, log_name: str) -> int | None:
        try:
            log_path = self._state.log_file(log_name)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("a")
            proc = subprocess.Popen(  # noqa: S603
                ["bun", "run", script],  # noqa: S607
                cwd=self._dir,
                env=self._child_env(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return proc.pid
        except OSError:
            return None

    def _collect_pids(self) -> list[int]:
        """Collect Next and Vite pids from files and listening ports."""
        pids: list[int] = []
        for name in (self.name, self._SPA_NAME):
            pid = self._state.read_pid(name)
            if pid:
                pids.append(pid)
        for port in (self._config.dev_port, self._config.spa_port):
            port_pid = pid_on_port(port)
            if port_pid:
                pids.append(port_pid)
        return list(set(pids))
