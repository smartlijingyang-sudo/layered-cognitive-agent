"""SimpleSafeExecutor plugin — named factory ``safe_executor.simple``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import SAFE_EXECUTOR_SIMPLE
from lca.contracts.protocols.infra import SafeExecutor
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="safe_executor.simple",
    provides=[SAFE_EXECUTOR_SIMPLE.key],
    implements=[SafeExecutor],
    layer="L1",
    effects="tools",
    description="Provide the SafeExecutor factory used by the Composer.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.ACT_SAFE_BOUNDARY,
        scope=Scope.INVOCATION,
        authority=(SAFE_EXECUTOR_SIMPLE.key,),
        evidence=("execution.safe-boundary.completed",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the named SafeExecutor factory ``safe_executor.simple``."""
    from lca.cognition.body.safe_executor import SimpleSafeExecutor

    ctx.provide(SAFE_EXECUTOR_SIMPLE.key, SimpleSafeExecutor)
