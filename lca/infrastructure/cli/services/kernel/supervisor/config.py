"""Supervisord-syntax config parsing for the kernel supervisor.

Parses ``[program:...]`` sections into :class:`ProgramConfig`
values, and builds the dev-default LCA program config.
"""

from __future__ import annotations

import configparser
import os
import shlex
import sys
from pathlib import Path

from lca.infrastructure.cli.services.kernel.supervisor.types import ProgramConfig

_TRUE = {"true", "yes", "1"}
_FALSE = {"false", "no", "0"}


def _parse_bool(raw: str, key: str) -> bool:
    lo = raw.strip().lower()
    if lo in _TRUE:
        return True
    if lo in _FALSE:
        return False
    raise ValueError(f"{key}: expected true/false/yes/no/1/0, got {raw!r}")


def _parse_int(raw: str, key: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key}: expected integer, got {raw!r}") from exc


def _parse_float(raw: str, key: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key}: expected number, got {raw!r}") from exc


def _parse_env(raw: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"environment: expected KEY=VAL pairs, got {part!r}")
        k, v = part.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"environment: empty key in {part!r}")
        env[k] = v.strip()
    return env


def parse_program_config(path: str | Path) -> list[ProgramConfig]:
    """Parse a supervisord-style config file into a list of programs."""
    # NOTE: allow_no_value defaults to False and is stored privately
    # (ConfigParser._allow_no_value); assigning it post-construction
    # would be a no-op, so it is simply left at the default.
    parser = configparser.ConfigParser()
    read = parser.read(path, encoding="utf-8")
    if not read:
        raise ValueError(f"config file unreadable or empty: {path}")

    programs: list[ProgramConfig] = []
    known_keys = {
        "command",
        "args",
        "directory",
        "autorestart",
        "startretries",
        "stopwaitsecs",
        "environment",
        "stdout_logfile",
        "stderr_logfile",
        "readiness_timeout",
    }
    for section in parser.sections():
        if not section.startswith("program:"):
            continue
        name = section[len("program:") :].strip()
        if not name:
            raise ValueError(f"{section}: empty program name")
        items = dict(parser.items(section))

        unknown = set(items) - known_keys
        if unknown:
            raise ValueError(f"[program:{name}]: unknown keys: {sorted(unknown)}")

        command = items.get("command", "")
        if not command:
            raise ValueError(f"[program:{name}]: command= is required")

        args_raw = items.get("args", "")
        args: tuple[str, ...] = tuple(shlex.split(args_raw)) if args_raw else ()

        programs.append(
            ProgramConfig(
                name=name,
                command=command,
                args=args,
                directory=items.get("directory", "") or os.getcwd(),
                autorestart=_parse_bool(items.get("autorestart", "true"), "autorestart"),
                startretries=_parse_int(items.get("startretries", "3"), "startretries"),
                stopwaitsecs=_parse_float(items.get("stopwaitsecs", "15"), "stopwaitsecs"),
                environment=(_parse_env(items["environment"]) if "environment" in items else {}),
                stdout_logfile=items.get("stdout_logfile") or None,
                stderr_logfile=items.get("stderr_logfile") or None,
                readiness_timeout=_parse_float(
                    items.get("readiness_timeout", "30"),
                    "readiness_timeout",
                ),
            )
        )
    if not programs:
        raise ValueError(f"{path}: no [program:...] sections found")
    return programs


def default_program_config(
    *,
    profile: str = "profiles/web-assistant.yaml",
    host: str = "0.0.0.0",
    port: int = 8765,
) -> ProgramConfig:
    """Build the dev-default LCA program."""
    return ProgramConfig(
        name="lca_kernel_dev",
        command=sys.executable,
        args=(
            "-m",
            "lca_kernel",
            "serve",
            "--profile",
            profile,
            "--host",
            host,
            "--port",
            str(port),
            "--allow-unknown-env",
        ),
        directory=os.getcwd(),
        autorestart=True,
        startretries=3,
        stopwaitsecs=15.0,
        environment={},
        stdout_logfile="/tmp/lca-kernel.stdout.log",
        stderr_logfile="/tmp/lca-kernel.stderr.log",
        readiness_timeout=30.0,
    )
