"""Sandbox execution contracts (ADR-0044).

Provider-neutral result shapes for code sandboxes. No I/O — pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default wall-clock budget for a single sandbox invocation (seconds).
DEFAULT_SANDBOX_TIMEOUT_S: int = 60

# Soft cap for stdout/stderr previews embedded in Observation.payload / ToolInvoked.
SANDBOX_PREVIEW_CHAR_LIMIT: int = 8000

# Guest path where tool-supplied attachment bytes are mounted (all backends).
SANDBOX_MOUNT_ROOT: str = "/mnt/data"

# Relative to SANDBOX_MOUNT_ROOT: guest dir whose files are collected as downloadable products.
# Full path: /mnt/data/outputs — files written elsewhere are not harvested (ADR-0046).
SANDBOX_OUTPUT_SUBDIR: str = "outputs"

# Caps for harvested generated_files (over-limit files skipped with diagnostics; run still succeeds).
SANDBOX_MAX_GENERATED_FILES: int = 20
SANDBOX_MAX_GENERATED_FILE_BYTES: int = 20 * 1024 * 1024

# Production Onlyboxes pythonExec image baseline (deploy/onlyboxes/requirements-python.txt).
# Ops contract for tool descriptions / prompts — not enforced by Sandbox Protocol.
SANDBOX_PREINSTALLED_PYTHON_PACKAGES: tuple[str, ...] = (
    "pandas",
    "numpy",
    "openpyxl",
    "xlsxwriter",
    "matplotlib",
    "seaborn",
    "pillow",
    "scipy",
    "requests",
    "tabulate",
)


@dataclass(frozen=True)
class SandboxFile:
    """One file produced (or mounted) by a sandbox run — bytes + display metadata."""

    name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class SandboxResult:
    """Terminal outcome of ``Sandbox.run`` (after streaming deltas have been emitted)."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    generated_files: tuple[SandboxFile, ...] = field(default_factory=tuple)
    error: str = ""
