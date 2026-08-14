#!/usr/bin/env python3
# ruff: noqa: S603, S607
"""lca-host — YAML-driven host runtime management.

Usage::

    scripts/lca-host.py provision <user>
    scripts/lca-host.py destroy   <user>
    scripts/lca-host.py status    [user]
    scripts/lca-host.py list
    scripts/lca-host.py env       <user>
    scripts/lca-host.py init                  # generate default lca-host.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lca.layer0_infra.host_runtime.config import DEFAULT_YAML, HostRuntimeConfig  # noqa: E402
from lca.layer0_infra.host_runtime.environment import HostEnvironment  # noqa: E402
from lca.layer0_infra.host_runtime.providers import ItemStatus  # noqa: E402

CONFIG_PATH = ROOT / "lca-host.yaml"

# ── formatters ────────────────────────────────────────────────────────

_ICONS = {
    ItemStatus.OK: "✅",
    ItemStatus.MISSING: "❌",
    ItemStatus.WARN: "⚠️",
    ItemStatus.ERROR: "❌",
}
_CYAN = "\033[1;36m"
_GREEN = "\033[1;32m"
_RED = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET = "\033[0m"


def _print_report(reports: list) -> None:
    for report in reports:
        print(f"\n{_CYAN}[{report.provider}]{_RESET}")
        for check in report.checks:
            icon = _ICONS.get(check.status, "?")
            color = (
                _GREEN
                if check.status == ItemStatus.OK
                else _RED
                if check.status == ItemStatus.MISSING
                else _YELLOW
            )
            detail = f" — {check.detail}" if check.detail else ""
            print(f"  {icon} {check.name}{color}{detail}{_RESET}")


# ── subcommands ───────────────────────────────────────────────────────


def cmd_init(_args: argparse.Namespace) -> None:
    if CONFIG_PATH.is_file():
        print(f"Config already exists: {CONFIG_PATH}")
        return
    CONFIG_PATH.write_text(DEFAULT_YAML, encoding="utf-8")
    print(f"✅ Generated {CONFIG_PATH}")
    print("   Edit it, then run: scripts/lca-host.py provision <user>")


def cmd_provision(args: argparse.Namespace) -> None:
    config = _load_config(args)
    env = HostEnvironment(config)
    print(f"\n{_CYAN}═══ provision: {args.user} ═══{_RESET}\n")
    ok = env.provision(args.user)
    print(f"\n{_CYAN}═══ status ═══{_RESET}")
    _print_report(env.status(args.user))
    sys.exit(0 if ok else 1)


def cmd_destroy(args: argparse.Namespace) -> None:
    config = _load_config(args)
    env = HostEnvironment(config)
    print(f"\n{_CYAN}═══ destroy: {args.user} ═══{_RESET}\n")
    env.destroy(args.user)
    print(f"\n{_CYAN}═══ done ═══{_RESET}")


def cmd_status(args: argparse.Namespace) -> None:
    config = _load_config(args)
    env = HostEnvironment(config)
    reports = env.status(args.user)
    _print_report(reports)
    all_ok = all(r.all_ok for r in reports)
    print(f"\n{'✅ all checks passed' if all_ok else '❌ some checks failed'}")
    sys.exit(0 if all_ok else 1)


def cmd_list(args: argparse.Namespace) -> None:
    config = _load_config(args)
    print(f"{'USER':<20} {'HOME':<25} {'DAEMON':<12} {'GATEWAY':<10}")
    print(f"{'----':<20} {'----':<25} {'------':<12} {'-------':<10}")
    for user in config.users:
        pid_file = Path(user.state_dir) / "connect.pid"
        daemon = "—"
        if pid_file.is_file():
            pid = int(pid_file.read_text().strip() or "0")
            try:
                os.kill(pid, 0)
                daemon = f"pid={pid}"
            except (ProcessLookupError, PermissionError):
                daemon = "stale"
        gw = "—"
        try:
            import subprocess

            r = subprocess.run(
                ["curl", "-sf", config.gateway.health_url], capture_output=True, timeout=3
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                gw = f"online={data.get('devices', {}).get('online', 0)}"
        except (OSError, json.JSONDecodeError, TimeoutError):
            gw = "—"
        print(f"{user.name:<20} {user.home:<25} {daemon:<12} {gw:<10}")


def cmd_env(args: argparse.Namespace) -> None:
    config = _load_config(args)
    user = config.find_user(args.user) or config.users[0] if config.users else None
    if not user:
        print("No users configured")
        return
    import socket

    print(f"Environment for {user.name}@{socket.gethostname()}\n")
    print(f"PATH={config.paths.venv_dir}/bin:{config.paths.managed_path}")
    print(f"VIRTUAL_ENV={config.paths.venv_dir}")
    print(f"HOME={user.home}\n")
    print("=== Tool resolution ===")
    venv_bin = Path(config.paths.venv_dir) / "bin"
    tool_dirs = [str(venv_bin), *config.paths.managed_path.split(":")]
    for tool in [
        "python3",
        "node",
        "npm",
        "uv",
        "officecli",
        "curl",
        "wget",
        "jq",
        "git",
        "ffmpeg",
        "pandoc",
    ]:
        resolved = None
        for d in tool_dirs:
            candidate = Path(d) / tool
            if candidate.is_file() and os.access(str(candidate), os.X_OK):
                resolved = str(candidate)
                break
        if resolved:
            import subprocess

            r = subprocess.run([resolved, "--version"], capture_output=True, text=True, timeout=5)
            ver = (r.stdout or r.stderr).strip().split("\n")[0]
            print(f"  {tool:<12} → {resolved}  ({ver})")
        else:
            print(f"  {tool:<12} → ❌ not found")


# ── main ──────────────────────────────────────────────────────────────


def _load_config(args: argparse.Namespace) -> HostRuntimeConfig:
    config_path = Path(getattr(args, "config", None) or CONFIG_PATH)
    return HostRuntimeConfig.from_yaml_or_default(config_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lca-host",
        description="LCA Host Runtime — YAML-driven environment management",
    )
    parser.add_argument("--config", "-c", help="Config file path (default: lca-host.yaml)")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Generate default lca-host.yaml")
    p_init.set_defaults(func=cmd_init)

    p_prov = sub.add_parser("provision", help="Provision shared layer + user")
    p_prov.add_argument("user", help="Username to provision")
    p_prov.set_defaults(func=cmd_provision)

    p_dest = sub.add_parser("destroy", help="Destroy user + workspace (shared preserved)")
    p_dest.add_argument("user", help="Username to destroy")
    p_dest.set_defaults(func=cmd_destroy)

    p_stat = sub.add_parser("status", help="Check system + user status")
    p_stat.add_argument("user", nargs="?", help="Check specific user (or all)")
    p_stat.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="List configured users")
    p_list.set_defaults(func=cmd_list)

    p_env = sub.add_parser("env", help="Show execution environment for a user")
    p_env.add_argument("user", nargs="?", help="Username")
    p_env.set_defaults(func=cmd_env)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
