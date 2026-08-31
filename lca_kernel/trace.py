"""BootTrace — in-memory snapshot of one boot's stage progress.

Public surface
--------------
- :class:`BootTrace` — frozen dataclass, no IO. The boot path appends to
  ``stages`` as each :class:`~lca_kernel.stages.Stage` finishes; the final
  ``outcome`` is set on success / failure / dispose. ``lca-ops logs
  --scope boot`` reads the same record from the journal; this trace is the
  per-process in-memory mirror used for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca_kernel.stages import Stage


@dataclass(frozen=True, slots=True)
class BootTrace:
    """In-memory snapshot of one boot's stages.

    ``stages`` is a chronologically ordered tuple of ``(stage, ts, status)``
    records. The trace never reaches disk; ``lca-ops`` reads the journal
    record for persistence. ``failure`` is the underlying exception when
    ``outcome == "failed"``; ``None`` otherwise.
    """

    profile_path: str
    started_at: float
    stages: tuple[tuple[Stage, float, Literal["ok", "failed"]], ...]
    outcome: Literal["booted", "failed", "disposed"]
    failure: BaseException | None = None


__all__ = ["BootTrace"]
