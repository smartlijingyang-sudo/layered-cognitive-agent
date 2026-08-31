"""Focus-aware STOP governance for declarative cognitive turns.

This contribution deliberately governs only whether a turn may continue after a
repeated, unsuccessful intent.  It reads already-reduced ``Turn`` facts and
returns a standard ``ControlVerdict``; it never mutates state, selects graph
edges, or performs an effect.  The harness remains the owner of journaling and
terminal projection.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.models.core.decision import Decision, Turn
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configuration for consecutive no-progress cognitive turns."""

    model_config = ConfigDict(extra="forbid")

    max_consecutive_stagnant_turns: int = Field(default=3, ge=1)


@dataclass(frozen=True, slots=True)
class FocusStopExecutor:
    """Stop an unchanged, unsuccessful intent after a bounded number of turns.

    A turn is stagnant only if it has an unsuccessful observation, its
    reflection explicitly reports correction/blockage, and its action intent is
    unchanged from the immediately preceding stagnant turn.  This deliberately
    leaves successful turns, intent changes, and incomplete reflection facts
    untouched so the policy neither guesses semantic equivalence nor replaces
    the tool-level circuit breaker.
    """

    max_consecutive_stagnant_turns: int = 3

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Return an auditable continuation or focus-closure verdict."""

        del input
        count = self._consecutive_stagnant_turns(context.state.history)
        if count >= self.max_consecutive_stagnant_turns:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail=(
                        "cognitive focus policy stopped repeated unsuccessful intent "
                        f"after {count} consecutive stagnant turns "
                        f"(limit={self.max_consecutive_stagnant_turns})"
                    ),
                    plugin_id="control.stop.focus",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail=(
                    "cognitive focus policy allows continuation "
                    f"(consecutive_stagnant_turns={count}, "
                    f"limit={self.max_consecutive_stagnant_turns})"
                ),
                plugin_id="control.stop.focus",
            ),
        )

    @staticmethod
    def _consecutive_stagnant_turns(history: Iterable[object]) -> int:
        """Count the trailing run of identical, reflected no-progress turns."""

        expected_intent: tuple[object, ...] | None = None
        count = 0
        for item in reversed(tuple(history)):
            if not isinstance(item, Turn) or not _is_stagnant(item):
                break
            intent = _intent_signature(item.decision)
            if expected_intent is None:
                expected_intent = intent
            elif intent != expected_intent:
                break
            count += 1
        return count


def _is_stagnant(turn: Turn) -> bool:
    """Return whether one durable Turn explicitly shows no cognitive progress."""

    reflection = turn.reflection
    return (
        not turn.observation.success
        and reflection is not None
        and reflection.verdict in {ReflectionVerdict.NEEDS_CORRECTION, ReflectionVerdict.BLOCKED}
    )


def _intent_signature(decision: Decision) -> tuple[object, ...]:
    """Build a conservative, deterministic identity for one declared intent."""

    action_type = str(decision.action_type)
    tool_names = tuple(call.tool_name for call in decision.tool_calls)
    delegation_targets = tuple(
        (delegation.target_role, delegation.target_agent_id) for delegation in decision.delegations
    )
    response = decision.response_text.strip() if decision.response_text else ""
    return action_type, tool_names, delegation_targets, response


@plugin(
    id="control.stop.focus",
    Config=Config,
    provides=["control.stop.focus"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.STOP,
            role=ContributionRole.GOVERN,
            executor="control.stop.focus",
            output="stop.focus",
            order=10,
            aggregation="deny-on-any-deny",
        )
    ],
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.STOP_DECIDE,
        scope=Scope.TURN,
        authority=("turn.read",),
        evidence=("control.stop.focus.checked",),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("control.stop.focus",),
        emits=("control.stop.focus.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Mount the profile-configured, read-only focus governance executor."""

    ctx.provide(
        "control.stop.focus",
        FocusStopExecutor(max_consecutive_stagnant_turns=config.max_consecutive_stagnant_turns),
    )


__all__ = ["Config", "FocusStopExecutor", "setup"]
