"""Fan-out strategy factory — registers into team_strategies.

同文件承载 ParallelStrategy —— CHOREOGRAPHY: concurrent members + optional
synthesizer。
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.atoms.telemetry import ATTR_CANDIDATE_COUNT, ATTR_SYNTHESIS_METHOD, SpanName
from lca.contracts.capabilities import STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_FAN_OUT
from lca.contracts.protocols import Synthesizer, TeamAssembly, TeamStage, TeamStrategy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability import span


class ParallelStrategy(TeamStrategy):
    """Run all members concurrently; optional Synthesizer aggregates results."""

    def __init__(self, stage: TeamStage, synthesizer: Synthesizer | None = None) -> None:
        self._stage = stage
        self._synthesizer = synthesizer

    async def run(self, objective: str) -> Result:
        members = self._stage.members
        if not members:
            return Result.failed("No members in team")
        raw = await asyncio.gather(
            *[self._stage.invoker.invoke(member, objective) for member in members],
            return_exceptions=True,
        )
        results = [_to_result(r) for r in raw]
        total_steps = sum(r.total_steps for r in results)

        if self._synthesizer is not None:
            ok_results = [r for r in results if r.status == TaskStatus.COMPLETED]
            if not ok_results:
                return Result.failed("All parallel members failed")
            with span(
                SpanName.TEAM_SYNTHESIS,
                **{
                    ATTR_CANDIDATE_COUNT: len(ok_results),
                    ATTR_SYNTHESIS_METHOD: type(self._synthesizer).__name__,
                },
            ):
                synthesized = await self._synthesizer.synthesize(objective, ok_results)
            synthesized.total_steps = total_steps
            return synthesized

        # 无 synthesizer：合并所有成功成员的输出
        ok_results = [r for r in results if r.status == TaskStatus.COMPLETED and r.output]
        if not ok_results:
            return Result.failed("All parallel members failed")
        if len(ok_results) == 1:
            out = ok_results[0]
            out.total_steps = total_steps
            return out
        budget = create_budget()
        budget.used_steps = total_steps
        return Result(
            trace_id=objective[:16],
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=total_steps,
            budget_used=budget,
            output="\n".join(str(r.output) for r in ok_results),
        )


def _to_result(raw: object) -> Result:
    """将 gather 结果（Result | BaseException）统一为 Result。"""
    if isinstance(raw, BaseException):
        return Result.failed(f"parallel member error: {raw}")
    return raw  # type: ignore[return-value]


def build_fan_out_strategy(assembly: TeamAssembly) -> Any:
    from lca.cognition.brain.synthesizer import ConcatSynthesizer

    return ParallelStrategy(assembly.stage, synthesizer=ConcatSynthesizer())


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.fan_out",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register fan_out TeamStrategy factory.",
    test_suite="tests/test_parallel_strategy.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_fan_out.checked", "strategy_fan_out.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_FAN_OUT, build_fan_out_strategy)
