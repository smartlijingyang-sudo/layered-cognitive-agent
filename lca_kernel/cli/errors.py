"""Kernel exception hierarchy (K6/K7 fail-loud surfaces).

Public surface
--------------
- :exc:`KernelError` — base for every error raised by the kernel.
- :exc:`FailLoudError` — K6 fail-loud path; downstream handlers turn this
  into ``process.exit(1)`` after teardown (see ADR-0117 §决定 2).
- :exc:`StageError` — K3 boot stage error; carries which :class:`~lca_kernel.stages.Stage`
  failed so the failure trace can pinpoint the offending phase.
- :exc:`ReloadError` — K8 HMR path; carries ``path`` + ``reason`` for supervisor
  decision (see ADR-0118 §决定 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal


class KernelError(Exception):
    """Base class for every kernel-raised exception.

        Plugin setup failures, ``.env`` whitelist violations, and shutdown
        coordination errors all derive from this type so a single ``except
    20→ KernelError`` clause catches them at the transport / CLI boundary.
    """


class FailLoudError(KernelError):
    """K6 fail-loud: signal an unhandled rejection / uncaught exception.

    The lifecycle coordinator converts this into ``sys.exit(1)`` after a
    bounded teardown window (``FAIL_LOUD_RELEASE_TIMEOUT_MS``).
    """


class StageError(KernelError):
    """K3 boot stage error — carries the failing :class:`Stage` identifier."""

    def __init__(self, stage: object, message: str) -> None:
        super().__init__(f"[stage={getattr(stage, 'name', stage)}] {message}")
        self.stage = stage


ReloadReason = Literal["missing", "shape", "empty", "io"]


class ReloadError(KernelError):
    """K8 HMR: reload path raised by ``PatchWatcher.reload_now()``.

    Carries the offending ``path`` and a coarse ``reason`` so the
    supervisor (uvicorn --reload / k8s readiness / lca-ops restart) can
    log + decide. See ADR-0118 §决定 4.
    """

    def __init__(self, path: Path, reason: ReloadReason, message: str) -> None:
        super().__init__(f"[reload:{reason}] {path}: {message}")
        self.path = path
        self.reason = reason


__all__ = ["FailLoudError", "KernelError", "ReloadError", "ReloadReason", "StageError"]
