"""Candidate-only profile evolution evaluator.

The service compares already-produced evaluation outcomes.  It has no file,
network, Composer, or profile resolver dependency and therefore cannot apply a
candidate, alter a grant, or mutate a production Profile.  Promotion remains an
explicit external approval concern.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import LEARNING_PROFILE_EVOLVER
from lca.contracts.harness.eval_comparison import EvalComparison
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ProfileEvolutionDecision:
    """Evidence-only recommendation for a versioned profile candidate."""

    candidate_ref: str
    status: str
    baseline_pass_rate: float
    candidate_pass_rate: float
    sample_size: int
    required_improvement: float
    reason: str


@dataclass(frozen=True, slots=True)
class ProfileEvolverService:
    """Evaluate candidate quality without applying or publishing a profile."""

    enabled: bool
    min_sample_size: int
    commit_threshold: float
    rollback_on_regression: bool

    def evaluate(
        self,
        *,
        candidate_ref: str,
        baseline: Sequence[EvalComparison],
        candidate: Sequence[EvalComparison],
    ) -> ProfileEvolutionDecision:
        """Return ``draft``/``rejected``/``approved_for_review`` from frozen results.

        ``approved_for_review`` is intentionally not a publish action.  A
        separately authorized promotion gate must validate provenance and apply
        any profile change after human approval.
        """

        sample_size = min(len(baseline), len(candidate))
        if not self.enabled:
            return self._decision(
                candidate_ref, "rejected", 0.0, 0.0, sample_size, "profile evolution disabled"
            )
        if not candidate_ref.strip():
            raise ValueError("candidate_ref must not be empty")
        if sample_size < self.min_sample_size:
            return self._decision(
                candidate_ref,
                "draft",
                self._pass_rate(baseline[:sample_size]),
                self._pass_rate(candidate[:sample_size]),
                sample_size,
                "insufficient held-out evaluation sample",
            )
        baseline_rate = self._pass_rate(baseline[:sample_size])
        candidate_rate = self._pass_rate(candidate[:sample_size])
        improvement = candidate_rate - baseline_rate
        if improvement >= self.commit_threshold:
            return self._decision(
                candidate_ref,
                "approved_for_review",
                baseline_rate,
                candidate_rate,
                sample_size,
                "passes held-out improvement threshold; manual promotion still required",
            )
        status = "rejected" if improvement < 0 and self.rollback_on_regression else "draft"
        reason = (
            "candidate regressed against baseline"
            if improvement < 0
            else "improvement below threshold"
        )
        return self._decision(
            candidate_ref,
            status,
            baseline_rate,
            candidate_rate,
            sample_size,
            reason,
        )

    def _decision(
        self,
        candidate_ref: str,
        status: str,
        baseline_rate: float,
        candidate_rate: float,
        sample_size: int,
        reason: str,
    ) -> ProfileEvolutionDecision:
        return ProfileEvolutionDecision(
            candidate_ref=candidate_ref,
            status=status,
            baseline_pass_rate=baseline_rate,
            candidate_pass_rate=candidate_rate,
            sample_size=sample_size,
            required_improvement=self.commit_threshold,
            reason=reason,
        )

    @staticmethod
    def _pass_rate(comparisons: Sequence[EvalComparison]) -> float:
        return sum(item.passed for item in comparisons) / len(comparisons) if comparisons else 0.0


class Config(BaseModel):
    """Candidate evaluation gates declared by the owning scenario bundle."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    ab_test_size: int = Field(default=20, ge=1)
    commit_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    rollback_on_regression: bool = True


@plugin(
    id="lca-profile-evolver",
    provides=[LEARNING_PROFILE_EVOLVER.key],
    requires=[],
    implements=["ProfileEvolverService"],
    layer="L2",
    effects="none",
    description="Evaluate profile candidates from frozen results; never auto-apply or publish.",
    test_suite="tests/architecture/test_self_improving_plugins.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the profile-candidate evaluator selected by the scenario bundle."""

    ctx.provide(
        LEARNING_PROFILE_EVOLVER.key,
        ProfileEvolverService(
            enabled=config.enabled,
            min_sample_size=config.ab_test_size,
            commit_threshold=config.commit_threshold,
            rollback_on_regression=config.rollback_on_regression,
        ),
    )


__all__ = ["Config", "ProfileEvolutionDecision", "ProfileEvolverService"]
