"""Infrastructure service — docker-compose (postgres, redis, s3).

Lifecycle: docker compose up -d / down.
Health: TCP port checks for each service.
Setup: ensure compose file exists, copy .env if needed.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

from lca.infrastructure.cli.config import InfraConfig
from lca.infrastructure.cli.service import HealthCheck, ServiceState, ServiceStatus


class InfraService:
    """Docker-compose infrastructure.

    Manages postgres, redis, and s3 via docker compose.
    """

    def __init__(self, config: InfraConfig, state_dir: Path) -> None:
        self.name = "infra"
        self._config = config
        self._state_dir = state_dir

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Bring missing endpoints up. Reuse already-running containers."""
        current = self.state()
        if current.is_running:
            return current

        compose_dir = self._compose_dir()
        if not compose_dir:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=current.checks,
                detail="compose file not found",
                why="lobehub-ui/docker-compose/dev/docker-compose.yml is missing",
            )

        env_file = compose_dir / ".env"
        if not env_file.exists():
            example = compose_dir / ".env.example"
            if example.exists():
                env_file.write_text(example.read_text())

        missing = [check.name for check in current.checks if not check.ok]
        wanted = missing or list(self._config.services)
        errors: list[str] = []
        for name in wanted:
            service = self._compose_service(name)
            try:
                result = subprocess.run(
                    ["docker", "compose", "up", "-d", service],
                    cwd=compose_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except FileNotFoundError:
                errors.append("docker is not installed")
                break
            except subprocess.TimeoutExpired:
                errors.append(f"{service}: docker compose timed out")
                continue
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip().splitlines()
                tail = err[-1] if err else f"exit {result.returncode}"
                errors.append(f"{service}: {tail}")

        after = self.state()
        if errors and not after.is_running:
            why = "; ".join(errors)
            return ServiceState(
                status=after.status,
                checks=after.checks,
                detail=after.detail,
                why=why,
                next_action="",
            )
        return after

    def stop(self) -> ServiceState:
        """Stop infrastructure services."""
        compose_dir = self._compose_dir()
        if compose_dir:
            try:
                subprocess.run(
                    ["docker", "compose", "down"],
                    cwd=compose_dir,
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass

        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        """Restart infrastructure."""
        self.stop()
        return self.start()

    # ── Setup ─────────────────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Ensure infrastructure prerequisites are met."""
        compose_dir = self._compose_dir()
        if not compose_dir:
            return False

        # Ensure .env
        env_file = compose_dir / ".env"
        if not env_file.exists():
            example = compose_dir / ".env.example"
            if example.exists():
                env_file.write_text(example.read_text())
                return True

        return False

    # ── Health ────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Check infrastructure health via port probes."""
        checks: list[HealthCheck] = []
        all_ok = True

        for svc_name, port in self._config.ports.items():
            ok = self._port_open(self._config.host, port)
            checks.append(HealthCheck(svc_name, ok, f":{port}"))
            if not ok:
                all_ok = False

        missing = [c.name for c in checks if not c.ok]
        if all_ok:
            status = ServiceStatus.RUNNING
            detail = "all services reachable"
            why = ""
            next_action = ""
        elif any(c.ok for c in checks):
            status = ServiceStatus.DEGRADED
            detail = "some services unreachable"
            why = f"unreachable: {', '.join(missing)}"
            next_action = ""
        else:
            status = ServiceStatus.STOPPED
            detail = "no services reachable"
            why = "postgres/redis ports are closed — LobeHub login/storage will fail"
            next_action = ""

        return ServiceState(
            status=status,
            checks=tuple(checks),
            detail=detail,
            why=why,
            next_action=next_action,
        )

    def heal(self) -> ServiceState:
        """Start whatever is still down. Never ask the operator to retry start."""
        return self.start()

    # ── Internals ─────────────────────────────────────────────────────

    def _compose_dir(self) -> Path | None:
        """Find the docker-compose directory."""
        path = Path(self._config.compose_dir)
        compose_file = path / "docker-compose.yml"
        if compose_file.exists():
            return path
        return None

    def _compose_service(self, endpoint: str) -> str:
        """Map a health-check name to a compose service name."""
        aliases = {"postgres": "postgresql", "s3": "rustfs"}
        return aliases.get(endpoint, endpoint)

    @staticmethod
    def _port_open(host: str, port: int, timeout: float = 1.5) -> bool:
        """Check if a TCP port is open."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, ConnectionRefusedError):
            return False
