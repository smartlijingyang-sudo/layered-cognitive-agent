"""Sandbox workspace bootstrap — LobeHub ``bootstrap.ts`` parity (ADR-0046).

Ensures guest workspace directories exist before any tool execution.
Attachment staging uses LCA ``write_files`` (FileStore); this module owns
directory init and the shared init marker constant.
"""

from __future__ import annotations

from lca.layer0_infra.sandbox.paths import ONLYBOXES

# LobeHub marker name — single source of truth for idempotent file sync (``bootstrap.ts``).
SANDBOX_FILES_INIT_MARKER = ONLYBOXES.init_marker

SANDBOX_INIT_TIMEOUT_S = 120


def sandbox_output_path() -> str:
    """Absolute guest path for harvestable outputs."""
    return ONLYBOXES.outputs_dir


def build_workspace_init_command() -> str:
    """Idempotent shell command: create upload root and outputs directory.

    Mirrors LobeHub ``buildSandboxFilesInitCommand`` when there are no downloads
    plus LCA ADR-0046 outputs subdir.
    """
    return f"mkdir -p '{ONLYBOXES.root}' '{ONLYBOXES.outputs_dir}'"
