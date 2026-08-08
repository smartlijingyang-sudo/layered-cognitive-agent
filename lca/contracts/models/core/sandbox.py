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
