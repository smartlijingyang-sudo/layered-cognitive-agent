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

from lca.layer0_infra.ops.config import GatewayConfig, LobeHubConfig
from lca.layer0_infra.ops.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    free_port,
    http_ready,
    kill_tree,
    pid_alive,
    pid_on_port,
)
from lca.layer0_infra.ops.state import StateStore


class LobeHubService:
    """LobeHub Next.js frontend.

    Manages the complete frontend lifecycle: source sync, patches, env,
    dependencies, and dev server.
    """

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
        """Start the dev server if not already running."""
        current = self.state()
        if current.is_running:
            return current

        # Ensure prerequisites
        self.ensure_ready()

        pid = self._spawn_dev()
        if pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="spawn failed")

        # Wait for ready — require consecutive successes so we don't
        # report ready during a brief compilation window.
        needed = 3
        consec = 0
        for _ in range(120):
            time.sleep(0.5)
            if http_ready(f"{self._config.dev_url}/", timeout=1.0):
                consec += 1
                if consec >= needed:
                    self._state.write_pid(self.name, pid)
                    return ServiceState(
                        status=ServiceStatus.RUNNING,
                        pid=pid,
                        port=self._config.dev_port,
                        detail="dev server ready",
                    )
            else:
                consec = 0

        return ServiceState(
            status=ServiceStatus.STOPPED,
            pid=pid,
            detail="dev server start timeout",
        )

    def stop(self) -> ServiceState:
        """Stop the dev server and all related processes."""
        pids = self._collect_pids()
        for pid in pids:
            kill_tree(pid)

        time.sleep(0.5)
        free_port(self._config.dev_port)
        self._state.remove_pid(self.name)

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

        # Reconcile PID: ``bun run dev`` may exit while next-server keeps serving.
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
        if dev_ok:
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
        """Auto-recover: start if stopped, re-apply patches if stale."""
        current = self.state()
        if current.is_running and not current.next_action:
            return current

        # Patches stale or missing → stop, re-ensure, restart
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
            subprocess.run(
                ["bash", str(sync_script)],
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
            subprocess.run(
                ["python3", str(patch_script)],
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
                ["bun", "install"],
                cwd=self._dir,
                capture_output=True,
                timeout=300,
            )
            return True
        except Exception:
            return False

    # ── Lifecycle Internals ───────────────────────────────────────────

    def _spawn_dev(self) -> int | None:
        """Spawn the dev server process."""
        import os

        try:
            # Inherit current environment and override specific variables
            env = {
                **os.environ,
                "PORT": str(self._config.dev_port),
                "OPENAI_PROXY_URL": f"{self._gateway.base_url}/v1",
                "OPENAI_API_KEY": "lca-local",
                "ENABLED_OPENAI": "1",
            }

            # Write logs to .lca-ops/lobehub.log
            log_path = self._state.log_file(self.name)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("a")

            proc = subprocess.Popen(
                ["bun", "run", "dev"],
                cwd=self._dir,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return proc.pid
        except Exception:
            return None

    def _collect_pids(self) -> list[int]:
        """Collect all PIDs related to the dev server."""
        pids = []

        # Main PID
        pid = self._state.read_pid(self.name)
        if pid:
            pids.append(pid)

        # Find by port
        port_pid = pid_on_port(self._config.dev_port)
        if port_pid:
            pids.append(port_pid)

        return list(set(pids))
