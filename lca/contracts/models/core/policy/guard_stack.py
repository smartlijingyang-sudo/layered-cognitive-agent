"""Guard stack layering — Hermes convergence + DSH guard tiers (ADR-0197)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GuardTier = Literal[
    "hard",  # iteration budget, wall clock, monotonic deny — cannot override
    "cooperative",  # timeout, checkpoint flush — structured synthetic result
    "advisory",  # repeat warn, progress nudge — PolicyFact / notice only
    "semantic",  # delivery / convergence — rewrite Decision to RESPOND
]

GuardPlane = Literal[
    "think",  # DecisionGate chain (GateService slot=loop)
    "stop",  # budget exhaustion / grace respond
    "act",  # ToolExecutionPipeline stages
    "graph",  # declarative loop guard (max_iterations re-entry)
]


@dataclass(frozen=True, slots=True)
class GuardStackLayer:
    """Catalog entry describing one guard contribution in the stack."""

    id: str
    tier: GuardTier
    plane: GuardPlane
    dsh_analog: str = ""
    hermes_analog: str = ""


GUARD_STACK_CATALOG: tuple[GuardStackLayer, ...] = (
    GuardStackLayer(
        id="gate.repeat-tool-call",
        tier="advisory",
        plane="think",
        dsh_analog="repeat-tool-reminder",
        hermes_analog="stall_guard identical-call notice",
    ),
    GuardStackLayer(
        id="gate.tool-loop-breaker",
        tier="hard",
        plane="think",
        dsh_analog="(post-execute stall detection → hard deny)",
        hermes_analog="ToolCallGuardrailController hard_stop",
    ),
    GuardStackLayer(
        id="gate.progress-loop-detector",
        tier="advisory",
        plane="think",
        dsh_analog="repeat-tool-reminder (cross-tool)",
        hermes_analog="no_progress_warn_after",
    ),
    GuardStackLayer(
        id="gate.delivery-satisfied",
        tier="semantic",
        plane="think",
        hermes_analog="verify-on-stop / delivery predicate",
    ),
    GuardStackLayer(
        id="gate.terminal-respond",
        tier="semantic",
        plane="think",
        hermes_analog="turn_finalizer budget respond",
    ),
    GuardStackLayer(
        id="convergence.policy.default",
        tier="semantic",
        plane="stop",
        hermes_analog="iteration_budget + turn_finalizer grace",
    ),
    GuardStackLayer(
        id="guard.tool-timeout",
        tier="cooperative",
        plane="act",
        dsh_analog="timeout-policy",
    ),
    GuardStackLayer(
        id="guard.tool-result-spill",
        tier="cooperative",
        plane="act",
        dsh_analog="spill-policy",
    ),
    GuardStackLayer(
        id="lca-declarative-loop-guard",
        tier="hard",
        plane="graph",
        hermes_analog="IterationBudget",
    ),
)

__all__ = [
    "GUARD_STACK_CATALOG",
    "GuardPlane",
    "GuardStackLayer",
    "GuardTier",
]
