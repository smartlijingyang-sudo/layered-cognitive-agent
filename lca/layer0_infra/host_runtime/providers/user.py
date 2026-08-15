"""Per-user providers: account, workspace, CLI daemon.

Each UserConfig gets one instance of each.
"""

# ruff: noqa: S603, S607

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from lca.layer0_infra.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.layer0_infra.host_runtime.providers import CheckResult, Provider, StatusReport


class UserProvider(Provider):
    """System user CRUD.  Cleans stale groups on create, kills processes on destroy."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        return f"user:{self.user.name}"

    @property
    def _exists(self) -> bool:
        r = self.run(["id", "-u", self.user.name])
        return r.returncode == 0

    def provision(self) -> bool:
        if self._exists:
            return True
        # Clean stale group from a previous userdel
        self.run_sudo(["groupdel", self.user.name])
        r = self.run_sudo(
            [
                "useradd",
                "--system",
                "--create-home",
                "--home-dir",
                self.user.home,
                "--shell",
                self.user.shell,
                self.user.name,
            ]
        )
        return r.returncode == 0

    def destroy(self) -> bool:
        if not self._exists:
            return True
        # Kill all user processes first
        self.run(["pkill", "-9", "-u", self.user.name])
        time.sleep(1)
        self.run_sudo(["userdel", "-r", self.user.name])
        self.run_sudo(["groupdel", self.user.name])
        return not self._exists

    def status(self) -> StatusReport:
        report = StatusReport(self.name)
        if self._exists:
            r = self.run(["id", self.user.name])
            report.ok(self.user.name, r.stdout.strip())
        else:
            report.fail(self.user.name, "does not exist")
        return report


class WorkspaceProvider(Provider):
    """Home directory, outputs/, .lca/ state dir, ownership."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        return f"workspace:{self.user.name}"

    def provision(self) -> bool:
        home = self.user.home
        self.run_sudo(["mkdir", "-p", home])
        self.run_sudo(["mkdir", "-p", self.user.outputs_dir])
        self.run_sudo(["mkdir", "-p", self.user.state_dir])
        self.run_sudo(["chown", "-R", f"{self.user.name}:{self.user.name}", home])
        self.run_sudo(["chmod", "2770", home])
        return True

    def destroy(self) -> bool:
        if Path(self.user.home).is_dir():
            self.run_sudo(["rm", "-rf", self.user.home])
        return not Path(self.user.home).is_dir()

    def status(self) -> StatusReport:
        report = StatusReport(self.name)
        home = Path(self.user.home)
        if home.is_dir():
            report.ok("home", self.user.home)
            outputs = Path(self.user.outputs_dir)
            if outputs.is_dir():
                report.ok("outputs", self.user.outputs_dir)
            else:
                report.fail("outputs")
            # Check ownership
            st = home.stat()
            report.ok("permissions", f"{st.st_mode:#o}")
        else:
            report.fail("home", f"{self.user.home} missing")
        return report


class CLIProvider(Provider):
    """Build + deploy lca-cli to cli_dir, manage daemon per user."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig | None = None) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        suffix = f":{self.user.name}" if self.user else ""
        return f"cli{suffix}"

    @property
    def _cli_js(self) -> Path:
        return Path(self.config.paths.cli_dir) / "dist" / "index.js"

    def provision(self) -> bool:
        """Build from source (if available) and deploy to cli_dir."""
        root = Path(".")
        src = root / self.config.cli.source_dir
        gw = root / self.config.cli.gateway_client_dir
        dest = Path(self.config.paths.cli_dir)

        # Build
        if (src / "src").is_dir():
            self.run(["npx", "tsc"], check=False)
            if (gw / "src").is_dir():
                import subprocess

                subprocess.run(["npx", "tsc"], cwd=str(gw), capture_output=True, timeout=60)

        if not (src / "dist" / "index.js").is_file():
            return False

        # Deploy
        self.run_sudo(["rm", "-rf", str(dest / "dist")])
        self.run_sudo(["cp", "-r", str(src / "dist"), str(dest)])

        # gateway-client
        if (gw / "dist").is_dir():
            gw_dest = dest / "node_modules" / "@lca" / "gateway-client"
            self.run_sudo(["mkdir", "-p", str(gw_dest)])
            self.run_sudo(["cp", "-r", str(gw / "dist"), str(gw_dest)])

        # Runtime deps
        for mod_dir in [src / "node_modules", gw / "node_modules"]:
            if mod_dir.is_dir():
                self.run_sudo(["cp", "-r", str(mod_dir / "*"), str(dest / "node_modules")])

        self.run_sudo(["chmod", "-R", "a+rX", str(dest)])

        # Wrapper
        wrapper_dest = Path(self.config.paths.tool_dir) / "lca"
        if not wrapper_dest.is_file():
            wrapper = f'#!/usr/bin/env bash\nexec node "{self._cli_js}" "$@"\n'
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(wrapper)
                f.flush()
                self.run_sudo(["cp", f.name, str(wrapper_dest)])
                self.run_sudo(["chmod", "+x", str(wrapper_dest)])
                Path(f.name).unlink(missing_ok=True)

        return True

    def start_daemon(self) -> bool:
        """Start the CLI connect daemon for this user."""
        if not self.user:
            return False
        if not self._cli_js.is_file():
            return False

        pid_file = Path(self.user.state_dir) / "connect.pid"

        # Already running?
        if pid_file.is_file():
            pid = int(pid_file.read_text().strip() or "0")
            if pid and self._pid_alive(pid):
                return True

        # Write start script (log redirect inside script for correct ownership)
        start_script = Path(self.user.state_dir) / "start.sh"
        script_content = f"""\
#!/bin/sh
export PATH="{self.config.paths.venv_dir}/bin:{self.config.paths.managed_path}"
export VIRTUAL_ENV={self.config.paths.venv_dir}
export HOME={self.user.home}
cd {self.user.home}
exec node {self._cli_js} connect \\
  --gateway {self.config.gateway.url} \\
  --workspace {self.user.home} \\
  --token-type serviceToken \\
  --token {self.config.gateway.token} \\
  >> "${{HOME}}/.lca/daemon.log" 2>&1
"""
        # Write via tempfile + sudo (dir owned by sandbox-user)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
            tmp.write(script_content)
            tmp.flush()
            self.run_sudo(["cp", tmp.name, str(start_script)])
            Path(tmp.name).unlink(missing_ok=True)
        self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(start_script)])
        self.run_sudo(["chmod", "755", str(start_script)])

        # Pre-create log
        log_file = Path(self.user.state_dir) / "daemon.log"
        self.run_sudo(["touch", str(log_file)])
        self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(log_file)])

        # Launch as sandbox-user (fully detached via setsid)
        import tempfile

        pass_file = Path(".lobehub-stack/sudo.pass")
        pw = pass_file.read_text().strip() if pass_file.is_file() else ""
        # Use setsid to fully detach, redirect all fds inside the script
        subprocess.run(
            [
                "sudo",
                "-S",
                "-p",
                "",
                "-u",
                self.user.name,
                "setsid",
                "bash",
                "-c",
                f"nohup {start_script} </dev/null >/dev/null 2>&1 &",
            ],
            input=pw,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        time.sleep(3)

        # Find PID
        r = self.run(["pgrep", "-u", self.user.name, "-f", "node.*index.js.*connect"])
        if r.returncode == 0 and r.stdout.strip():
            pid = int(r.stdout.strip().split("\n")[-1])
            self.run_sudo(["bash", "-c", f"echo '{pid}' > {pid_file}"])
            self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(pid_file)])
            return True
        return False

    def stop_daemon(self) -> bool:
        if not self.user:
            return True
        self.run(["pkill", "-u", self.user.name, "-f", "node.*index.js.*connect"])
        pid_file = Path(self.user.state_dir) / "connect.pid"
        if pid_file.is_file():
            self.run_sudo(["rm", "-f", str(pid_file)])
        return True

    def status(self) -> StatusReport:
        report = StatusReport(self.name)

        if self._cli_js.is_file():
            report.ok("deployed", str(self.config.paths.cli_dir))
        else:
            report.fail("deployed", "CLI not found")

        if self.user:
            pid_file = Path(self.user.state_dir) / "connect.pid"
            if pid_file.is_file():
                pid = int(pid_file.read_text().strip() or "0")
                if pid and self._pid_alive(pid):
                    report.ok("daemon", f"pid={pid}")
                else:
                    report.fail("daemon", "stale pid file")
            else:
                report.fail("daemon", "not running")

            # Gateway connectivity
            import subprocess

            try:
                r = subprocess.run(
                    ["curl", "-sf", self.config.gateway.health_url],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if r.returncode == 0:
                    import json

                    data = json.loads(r.stdout)
                    online = data.get("devices", {}).get("online", 0)
                    report.ok("gateway", f"online={online}")
                else:
                    report.warn("gateway", "unreachable")
            except Exception:
                report.warn("gateway", "unreachable")

        return report

    def heal(self, failed_check: CheckResult) -> bool:
        """Restart the daemon if it's down."""
        if failed_check.name == "daemon" and self.user:
            self.stop_daemon()
            return self.start_daemon()
        return False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we can't signal it — still alive
            return True
