"""Configurable default convergence policy (ADR-0196 + ADR-0197)."""

from __future__ import annotations

from dataclasses import dataclass

from lca.cognition.convergence.policy import DefaultConvergencePolicy
from lca.contracts.models.core.policy.convergence import (
    ConvergenceVerdict,
    DeliveryEvidence,
)
from lca.contracts.models.core.state.state import AgentState


@dataclass(frozen=True, slots=True)
class ConvergencePolicyConfig:
    producer_nudge_threshold: int = 3
    enable_producer_nudge: bool = True


class ConfigurableConvergencePolicy(DefaultConvergencePolicy):
    """Profile-tuned convergence policy over delivery evidence."""

    def __init__(self, config: ConvergencePolicyConfig) -> None:
        self._config = config

    def evaluate(self, state: AgentState, *, evidence: DeliveryEvidence) -> ConvergenceVerdict:
        del state
        if evidence.satisfied:
            return ConvergenceVerdict(
                kind="force_respond",
                rationale=evidence.detail,
                evidence=evidence,
            )
        if (
            self._config.enable_producer_nudge
            and evidence.producer_success_since_task >= self._config.producer_nudge_threshold
            and evidence.task_class == "informative_text"
        ):
            return ConvergenceVerdict(
                kind="nudge",
                rationale="多次 producer 成功但未收口；应 text respond",
                evidence=evidence,
            )
        return ConvergenceVerdict(
            kind="continue",
            rationale=evidence.detail or "continue",
            evidence=evidence,
        )


__all__ = ["ConfigurableConvergencePolicy", "ConvergencePolicyConfig"]
