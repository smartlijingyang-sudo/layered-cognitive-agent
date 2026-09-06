"""LoopGuardPolicy — profile-configurable think-plane thresholds (ADR-0197)."""

from __future__ import annotations

from typing import Protocol

from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds


class LoopGuardPolicy(Protocol):
    """Profile-selected loop hygiene thresholds for DecisionGate chain."""

    @property
    def thresholds(self) -> LoopPolicyThresholds: ...

    @property
    def repeat_thresholds(self) -> tuple[int, ...]: ...

    @property
    def arguments_preview_chars(self) -> int: ...


__all__ = ["LoopGuardPolicy"]
