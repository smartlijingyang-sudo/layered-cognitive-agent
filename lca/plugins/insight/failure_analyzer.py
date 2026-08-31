"""Deterministic, candidate-only failure analysis plugin.

The service does not alter a run, Profile, or capability.  It records a
traceable diagnosis input that an evaluator may later use to synthesize an
improvement candidate under separate review.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import LEARNING_FAILURE_ANALYZER
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.learning import FailureAnalysis, FailureAnalyzer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class FailureAnalyzerService(FailureAnalyzer):
    """Derive deterministic, non-authoritative analyses for allowed triggers."""

    enabled: bool
    triggers: frozenset[str]

    def analyze(
        self,
        *,
        run_ref: str,
        trigger: str,
        evidence_refs: tuple[str, ...],
        summary: str = "",
    ) -> FailureAnalysis | None:
        """Return an analysis only for configured triggers with real evidence."""

        if (
            not self.enabled
            or trigger not in self.triggers
            or not run_ref.strip()
            or not evidence_refs
        ):
            return None
        root_cause = summary.strip() or f"configured failure trigger: {trigger}"
        return FailureAnalysis(
            run_ref=run_ref,
            trigger=trigger,
            root_cause=root_cause,
            evidence_refs=tuple(evidence_refs),
            suggestions=(
                "Create an isolated candidate and evaluate it against a frozen holdout set.",
                "Do not modify grants, budgets, approvals, or runtime kernel bindings.",
            ),
        )


class Config(BaseModel):
    """Failure triggers declared by the owning learning scenario bundle."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    trigger: list[str] = Field(default_factory=list)


@plugin(
    id="lca-failure-analyzer",
    provides=[LEARNING_FAILURE_ANALYZER.key],
    requires=[],
    implements=["FailureAnalyzerService"],
    layer="L1",
    effects="none",
    description="Derive evidence-linked failure analyses without changing profiles or capabilities.",
    test_suite="tests/architecture/test_self_improving_plugins.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=("plugin.serve",),
        evidence=("lca-failure-analyzer.checked", "lca-failure-analyzer.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the configured read-only failure analyzer."""

    ctx.provide(
        LEARNING_FAILURE_ANALYZER.key,
        FailureAnalyzerService(enabled=config.enabled, triggers=frozenset(config.trigger)),
    )


__all__ = ["Config", "FailureAnalysis", "FailureAnalyzerService"]
