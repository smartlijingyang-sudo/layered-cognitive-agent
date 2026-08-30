"""Sandbox bootstrap helpers for run_skill_script."""

from __future__ import annotations

import json

from lca.contracts.protocols.operational_skills import SANDBOX_SKILL_MOUNT_PREFIX
from lca.infrastructure.credentials.sandbox_env import build_sandbox_env_preamble
from lca.infrastructure.sandbox.paths import ONLYBOXES


def skill_mount_dir(skill_id: str) -> str:
    return ONLYBOXES.join(SANDBOX_SKILL_MOUNT_PREFIX, skill_id)


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
    env_preamble = build_sandbox_env_preamble()
    return f"""
import os as _lca_os
import subprocess as _lca_sp
import sys as _lca_sys
from pathlib import Path as _lca_Path
{env_preamble}
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
