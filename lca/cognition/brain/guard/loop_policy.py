"""Static loop guard policy from profile config (ADR-0197)."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds


@dataclass(frozen=True, slots=True)
class LoopGuardPolicyView:
    """Profile-resolved loop guard configuration for think-plane gates."""

    thresholds: LoopPolicyThresholds
    repeat_thresholds: tuple[int, ...] = (3, 5, 8)
    arguments_preview_chars: int = 500


class StaticLoopGuardPolicy:
    """Immutable policy supplied by ``loop.policy.default`` plugin config."""

    def __init__(self, view: LoopGuardPolicyView) -> None:
        self._view = view

    @property
    def thresholds(self) -> LoopPolicyThresholds:
        return self._view.thresholds

    @property
    def repeat_thresholds(self) -> tuple[int, ...]:
        return self._view.repeat_thresholds

    @property
    def arguments_preview_chars(self) -> int:
        return self._view.arguments_preview_chars


__all__ = ["LoopGuardPolicyView", "StaticLoopGuardPolicy"]
