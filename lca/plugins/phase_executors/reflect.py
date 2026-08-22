"""标准 reflect PhaseExecutor。

在标准失败检测模式下:当 observation 不存在或 observation.success 为 False 时,
输出 `admit_recovery = True`,允许 recovery profile 触发 reflect → think 重入边。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_executors.common import (
    StandardPhaseConfig,
    StandardPhaseExecutor,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.reflect.standard",
    phase=SemanticPhase.REFLECT,
    module="lca.plugins.phase_executors.reflect",
)


@dataclass(frozen=True, slots=True)
class RecoveryReflectExecutor:
    """Reflect executor that detects failures and admits recovery.

    When observation.success is False (or observation is absent),
    emits a reflection payload with `admit_recovery = True` so the
    recovery edge (reflect → think) can be taken.
    """

    def _is_failure(self, observation: Any) -> bool:
        if observation is None:
            return True
        if isinstance(observation, Mapping):
            success = observation.get("success")
            return success is False or success is None
        return getattr(observation, "success", None) is False

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        observation = context.artifacts.get("act")
        is_failure = self._is_failure(observation)

        # Delegate to standard executor for base reflection
        base_executor = StandardPhaseExecutor(SemanticPhase.REFLECT)
        base_result = await base_executor.execute(context, input)

        # Recovery is edge-routing metadata, not a replacement for the
        # typed Reflection contract consumed by remember/stop policies.
        return PhaseResult(
            result_kind=base_result.result_kind,
            facts=base_result.facts,
            deltas=base_result.deltas,
            evidence_refs=base_result.evidence_refs,
            next_hints={**dict(base_result.next_hints), "admit_recovery": is_failure},
            payload=base_result.payload,
            command_envelope=base_result.command_envelope,
        )


@plugin(
    id="phase.reflect.standard",
    Config=StandardPhaseConfig,
    provides=("phase.reflect.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.reflect.standard", RecoveryReflectExecutor())


def create_executor() -> RecoveryReflectExecutor:
    return RecoveryReflectExecutor()
