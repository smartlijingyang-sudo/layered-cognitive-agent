"""Loop detection thresholds — profile-configurable gate policy (ADR-0191 R7)."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.policy.budget import TOOL_LOOP_BREAK_THRESHOLD


@dataclass(frozen=True, slots=True)
class LoopPolicyThresholds:
    """Layered loop policy thresholds.

    Layer 1 — repeat signal (warn only)
    Layer 2 — stalled identical observation (block)
    Layer 3 — consecutive failures (block)
    Layer 4 — cross-tool no progress (warn → block)
    Layer 5 — consecutive identical tool+args fingerprint (block). Default 2 to
        match the observed production distribution (most loops present at the
        second call); profile can raise to 3 for higher tolerance.
    """

    repeat_warn: int = 3
    break_failures: int = TOOL_LOOP_BREAK_THRESHOLD
    break_stalled: int = TOOL_LOOP_BREAK_THRESHOLD
    progress_warn: int = 3
    progress_break: int = 6
    consecutive_repeat_max: int = 2


DEFAULT_LOOP_POLICY = LoopPolicyThresholds()

__all__ = ["DEFAULT_LOOP_POLICY", "LoopPolicyThresholds"]
