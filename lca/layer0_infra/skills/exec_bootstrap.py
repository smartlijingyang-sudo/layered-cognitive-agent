"""Sandbox bootstrap helpers for run_skill_script."""

from __future__ import annotations

import json

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT
from lca.contracts.protocols.operational_skills import SANDBOX_SKILL_MOUNT_PREFIX


def skill_mount_dir(skill_id: str) -> str:
    return f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_SKILL_MOUNT_PREFIX}/{skill_id}"


def build_skill_exec_code(*, skill_id: str, command: str, install_requirements: bool) -> str:
    """Wrap a shell command with skill cwd + optional requirements install."""
    mount = skill_mount_dir(skill_id)
    cmd_literal = json.dumps(command)
    req_block = ""
    if install_requirements:
        req_block = f"""
_req = _lca_Path({mount!r}) / "requirements.txt"
if _req.is_file():
    import subprocess as _lca_sp
    _lca_sp.check_call(
        ["uv", "pip", "install", "--system", "-r", str(_req)],
        cwd={mount!r},
    )
"""
    return f"""
import os as _lca_os
import subprocess as _lca_sp
import sys as _lca_sys
from pathlib import Path as _lca_Path

_lca_root = {mount!r}
_lca_os.makedirs(_lca_root, exist_ok=True)
_lca_os.chdir(_lca_root)
{req_block}
_lca_proc = _lca_sp.run(
    {cmd_literal},
    shell=True,
    cwd=_lca_root,
    capture_output=True,
    text=True,
)
if _lca_proc.stdout:
    print(_lca_proc.stdout, end="" if _lca_proc.stdout.endswith("\\n") else "\\n", flush=True)
if _lca_proc.stderr:
    print(_lca_proc.stderr, end="" if _lca_proc.stderr.endswith("\\n") else "\\n", file=_lca_sys.stderr, flush=True)
if _lca_proc.returncode:
    raise SystemExit(_lca_proc.returncode)
"""


def skill_mount_files(
    skill_id: str,
    resource_files: dict[str, bytes],
) -> dict[str, bytes]:
    """Map store resources to Sandbox ``files`` mount keys."""
    prefix = f"{SANDBOX_SKILL_MOUNT_PREFIX}/{skill_id}"
    mounts: dict[str, bytes] = {}
    for rel, data in resource_files.items():
        mounts[f"{prefix}/{rel}"] = data
    return mounts
