"""Default loop guard policy plugin — profile-configurable thresholds (ADR-0197)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from lca.cognition.brain.guard.loop_policy import LoopGuardPolicyView, StaticLoopGuardPolicy
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import LOOP_GUARD_POLICY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.think.loop_guard import LoopGuardPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """DSH ``repeat-tool-reminder`` + Hermes guardrail threshold analog."""

    model_config = {"extra": "forbid"}

    repeat_warn: int = Field(default=3, ge=2)
    break_failures: int = Field(default=3, ge=2)
    break_stalled: int = Field(default=3, ge=2)
    progress_warn: int = Field(default=3, ge=2)
    progress_break: int = Field(default=6, ge=3)
    repeat_thresholds: list[int] = Field(default_factory=lambda: [3, 5, 8])
    arguments_preview_chars: int = Field(default=500, ge=64, le=4000)

    @field_validator("repeat_thresholds")
    @classmethod
    def _validate_repeat_thresholds(cls, values: list[int]) -> list[int]:
        if len(values) < 1:
            raise ValueError("repeat_thresholds must contain at least one entry")
        if len(values) != len(set(values)):
            raise ValueError("repeat_thresholds must not contain duplicates")
        if any(v < 2 for v in values):
            raise ValueError("repeat_thresholds entries must be >= 2")
        return sorted(values)


@plugin(
    id="loop.policy.default",
    provides=[LOOP_GUARD_POLICY.key],
    requires=[],
    implements=[LoopGuardPolicy],
    layer="L1",
    effects="none",
    description="Profile-configurable loop hygiene thresholds for think-plane gates.",
    test_suite="tests/cognition/test_loop_guard_policy_plugin.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.THINK_GUARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.AGENT, Scope.RUN)),
        authority=AuthorityContract(grants=("loop_policy.read",)),
        observability=EvidenceContract(descriptors=("loop.policy.default.provided",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    view = LoopGuardPolicyView(
        thresholds=LoopPolicyThresholds(
            repeat_warn=config.repeat_warn,
            break_failures=config.break_failures,
            break_stalled=config.break_stalled,
            progress_warn=config.progress_warn,
            progress_break=config.progress_break,
        ),
        repeat_thresholds=tuple(config.repeat_thresholds),
        arguments_preview_chars=config.arguments_preview_chars,
    )
    ctx.provide(LOOP_GUARD_POLICY.key, StaticLoopGuardPolicy(view))
