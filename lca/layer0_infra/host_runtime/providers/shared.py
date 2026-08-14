"""Shared providers: path, packages, tools, venv.

These manage system-level resources shared across all users.
"""

# ruff: noqa: S603

from __future__ import annotations

import shutil
from pathlib import Path

from lca.layer0_infra.host_runtime.providers import Provider, StatusReport


class PathProvider(Provider):
    """Ensure /etc/environment and /etc/profile.d contain the managed PATH."""

    @property
    def name(self) -> str:
        return "path"

    def provision(self) -> bool:
        mp = self.config.paths.managed_path

        # /etc/environment
        etc_env = Path(self.config.paths.etc_environment)
        line = f'PATH="{mp}"'
        if not etc_env.is_file() or mp not in etc_env.read_text():
            r = self.run_sudo(["bash", "-c", f"echo '{line}' > {etc_env}"])
            if r.returncode != 0:
                return False
            self.run_sudo(["chmod", "644", str(etc_env)])

        # /etc/profile.d/lca.sh
        pd = Path(self.config.paths.profile_d)
        content = f'export PATH="{mp}${{PATH:+:$PATH}}"'
        if not pd.is_file() or mp not in pd.read_text():
            r = self.run_sudo(["bash", "-c", f"echo '{content}' > {pd}"])
            if r.returncode != 0:
                return False
            self.run_sudo(["chmod", "644", str(pd)])

        return True

    def status(self) -> StatusReport:
        report = StatusReport("path")
        mp = self.config.paths.managed_path

        etc_env = Path(self.config.paths.etc_environment)
        if etc_env.is_file() and mp in etc_env.read_text():
            report.ok("/etc/environment")
        else:
            report.fail("/etc/environment", "missing managed PATH")

        pd = Path(self.config.paths.profile_d)
        if pd.is_file():
            report.ok("/etc/profile.d/lca.sh")
        else:
            report.fail("/etc/profile.d/lca.sh")

        return report


class PackagesProvider(Provider):
    """Install system packages (idempotent)."""

    @property
    def name(self) -> str:
        return "packages"

    def provision(self) -> bool:
        pkgs = self._packages_for_system()
        if not pkgs:
            return True
        mgr = self._package_manager()
        if mgr == "apt":
            r = self.run_sudo(["apt-get", "install", "-y", "--no-install-recommends", *pkgs])
        elif mgr == "dnf":
            r = self.run_sudo(["dnf", "install", "-y", "--setopt=install_weak_deps=False", *pkgs])
        elif mgr == "yum":
            r = self.run_sudo(["yum", "install", "-y", *pkgs])
        else:
            return True
        return r.returncode == 0

    def status(self) -> StatusReport:
        report = StatusReport("packages")
        for tool in ["pandoc", "ffmpeg", "jq", "curl", "wget", "git"]:
            path = self.which(tool)
            if path:
                report.ok(tool, path)
            else:
                report.fail(tool, "not found")
        return report

    @staticmethod
    def _package_manager() -> str:
        if shutil.which("apt-get"):
            return "apt"
        if shutil.which("dnf"):
            return "dnf"
        if shutil.which("yum"):
            return "yum"
        return ""

    def _packages_for_system(self) -> list[str]:
        mgr = self._package_manager()
        sp = self.config.system_packages
        return getattr(sp, mgr, [])


class ToolsProvider(Provider):
    """Copy key binaries into tool_dir so sandbox users can reach them."""

    @property
    def name(self) -> str:
        return "tools"

    def provision(self) -> bool:
        tool_dir = self.config.paths.tool_dir
        venv_py = Path(self.config.paths.venv_dir) / "bin" / "python3"

        # Prefer shared venv python (reportlab, pandas, …) over system python3.
        if venv_py.is_file():
            for alias in ("python3", "python"):
                dest = Path(tool_dir) / alias
                self.run_sudo(["rm", "-f", str(dest)])
                self.run_sudo(["ln", "-sf", str(venv_py), str(dest)])
                self.run_sudo(["chmod", "755", str(dest)])

        # python3 → python3.12 if system python is too old (when venv missing)
        if not venv_py.is_file():
            self._ensure_python_symlink(tool_dir)

        # copy uv, officecli (not symlink — sandbox-user can't traverse /home/<real-user>/)
        for binary_name in self.config.tools.names:
            if binary_name in {"python3", "python"}:
                continue
            src = self.which(binary_name)
            if not src:
                continue
            dest = Path(tool_dir) / binary_name
            if dest.is_file() and not dest.is_symlink():
                continue
            self.run_sudo(["rm", "-f", str(dest)])
            self.run_sudo(["cp", src, str(dest)])
            self.run_sudo(["chmod", "755", str(dest)])

        return True

    def _ensure_python_symlink(self, tool_dir: str) -> None:
        import re

        current = self.which("python3")
        if not current:
            return
        r = self.run([current, "--version"])
        m = re.search(r"(\d+)\.(\d+)", r.stdout)
        if not m:
            return
        major, minor = int(m.group(1)), int(m.group(2))
        req_major, req_minor = (int(x) for x in self.config.tools.python_min_version.split("."))
        if major > req_major or (major == req_major and minor >= req_minor):
            return
        for candidate in self.config.tools.python_candidates:
            if Path(candidate).is_file():
                dest = Path(tool_dir) / "python3"
                self.run_sudo(["ln", "-sf", candidate, str(dest)])
                return

    def status(self) -> StatusReport:
        report = StatusReport("tools")
        tool_dir = self.config.paths.tool_dir
        for binary_name in self.config.tools.names:
            for search_dir in [tool_dir, ""]:
                path = (
                    f"{tool_dir}/{binary_name}"
                    if search_dir == tool_dir
                    else self.which(binary_name) or ""
                )
                if path and Path(path).exists():
                    r = self.run([path, "--version"])
                    ver = (r.stdout or r.stderr).strip().split("\n")[0]
                    report.ok(binary_name, f"{ver} @ {path}")
                    break
            else:
                report.fail(binary_name)
        return report


class VenvProvider(Provider):
    """Shared Python venv with pre-installed packages."""

    @property
    def name(self) -> str:
        return "venv"

    def provision(self) -> bool:
        venv_dir = self.config.paths.venv_dir
        uv = self.which("uv")
        if not uv:
            return False

        if not Path(venv_dir).is_dir():
            Path(venv_dir).parent.mkdir(parents=True, exist_ok=True)
            r = self.run([uv, "venv", venv_dir, "--python", "3.12"])
            if r.returncode != 0:
                r = self.run([uv, "venv", venv_dir])
            if r.returncode != 0:
                return False

        req = Path(self.config.venv.requirements_file)
        if req.is_file():
            env = {"UV_INDEX_URL": self.config.venv.python_index}
            import os

            env.update(os.environ)
            import subprocess

            result = subprocess.run(
                [uv, "pip", "install", "--python", f"{venv_dir}/bin/python3", "-r", str(req)],
                env=env,
                capture_output=True,
                timeout=300,
            )
            if result.returncode != 0:
                return False

        venv_bin = Path(venv_dir) / "bin"
        py3 = venv_bin / "python3"
        py = venv_bin / "python"
        if py3.is_file() and not py.exists():
            py.symlink_to("python3")

        self.run_sudo(["chmod", "-R", "a+rX", venv_dir])
        self.run_sudo(["chmod", "a+rx", str(Path(venv_dir).parent)])
        return True

    def status(self) -> StatusReport:
        report = StatusReport("venv")
        venv_dir = self.config.paths.venv_dir
        py = Path(venv_dir) / "bin" / "python3"

        if not py.is_file():
            report.fail("venv", f"not found: {venv_dir}")
            return report

        r = self.run([str(py), "--version"])
        report.ok("python", (r.stdout or "").strip())

        imports = "; ".join(f"import {p}" for p in self.config.venv.check_imports)
        r = self.run([str(py), "-c", imports])
        if r.returncode == 0:
            report.ok("packages", f"{len(self.config.venv.check_imports)} importable")
        else:
            report.fail("packages", r.stderr[:100] if r.stderr else "import failed")

        return report
