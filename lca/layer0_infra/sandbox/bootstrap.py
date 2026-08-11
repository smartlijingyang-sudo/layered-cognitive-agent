"""Sandbox workspace bootstrap — LobeHub ``bootstrap.ts`` parity (ADR-0046).

Ensures guest workspace directories exist before any tool execution.
Attachment staging uses LCA ``write_files`` (FileStore); this module owns
directory init and the shared init marker constant.
"""

from __future__ import annotations

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR

# LobeHub marker name — single source of truth for idempotent file sync (``bootstrap.ts``).
SANDBOX_FILES_INIT_MARKER = f"{SANDBOX_MOUNT_ROOT}/.lobe-files-initialized"

SANDBOX_INIT_TIMEOUT_S = 120


def sandbox_output_path() -> str:
    """Absolute guest path for harvestable outputs."""
    return f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}"


def build_workspace_init_command() -> str:
    """Idempotent shell command: create upload root and outputs directory.

    Mirrors LobeHub ``buildSandboxFilesInitCommand`` when there are no downloads
    (``mkdir -p /mnt/data``) plus LCA ADR-0046 outputs subdir.
    """
    root = SANDBOX_MOUNT_ROOT
    outputs = sandbox_output_path()
    return f"mkdir -p '{root}' '{outputs}'"
