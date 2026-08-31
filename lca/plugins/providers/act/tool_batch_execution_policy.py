"""Profile provider for scheduling a model-emitted batch of tool calls."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from lca.cognition.body.tool_batch_execution import (
    ParallelToolBatchExecutionPolicy,
    SafeToolBatchExecutionPolicy,
    SegmentedSafeToolBatchExecutionPolicy,
    SequentialToolBatchExecutionPolicy,
)
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import TOOL_BATCH_EXECUTION_POLICY
from lca.contracts.protocols.act.tool_batch_execution import ToolBatchExecutionPolicy
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Choose one profile-owned tool-batch scheduling strategy."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["safe", "segmented_safe", "parallel", "sequential"] = "safe"


def build_tool_batch_execution_policy(mode: str) -> ToolBatchExecutionPolicy:
    """Construct one validated scheduling strategy without ambient configuration."""

    policies: dict[str, ToolBatchExecutionPolicy] = {
        "safe": SafeToolBatchExecutionPolicy(),
        "segmented_safe": SegmentedSafeToolBatchExecutionPolicy(),
        "parallel": ParallelToolBatchExecutionPolicy(),
        "sequential": SequentialToolBatchExecutionPolicy(),
    }
    try:
        return policies[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported tool batch execution mode: {mode!r}") from exc


@plugin(
    id="lca-tool-batch-execution-policy",
    requires=[],
    provides=[TOOL_BATCH_EXECUTION_POLICY.key],
    implements=[ToolBatchExecutionPolicy],
    layer="L1",
    effects="none",
    kind=PluginKind.PRIMITIVE,
    description=(
        "Provide a profile-selected safe, segmented-safe, parallel, or sequential "
        "strategy for model-emitted multi-tool batches without changing Body or SafeExecutor."
    ),
    test_suite="tests/cognition/body/test_tool_batch_execution.py",
    functional_group=FunctionalGroup.G7_EXECUTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.ACT_EXECUTE,
        scope=Scope.TURN,
        authority=(TOOL_BATCH_EXECUTION_POLICY.key,),
        evidence=("tool.batch.execution.planned",),
        revision="v1",
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose one pure scheduling policy to the action-handler provider."""

    ctx.provide(TOOL_BATCH_EXECUTION_POLICY.key, build_tool_batch_execution_policy(config.mode))


__all__ = ["Config", "build_tool_batch_execution_policy", "setup"]
