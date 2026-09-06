"""Tool result spill guard plugin — DSH spill-policy (ADR-0197)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.cognition.body.guard.spill import ToolResultSpillGuard
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}

    max_inline_bytes: int = Field(default=50_000, ge=1024)


@plugin(
    id="guard.tool-result-spill",
    requires=["tool_guards"],
    layer="L1",
    effects="none",
    description="Bound inline tool results; spill oversized payloads (DSH spill-policy).",
    test_suite="tests/cognition/test_tool_guard_plugins.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_SAFE_BOUNDARY,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.INVOCATION,)),
        authority=AuthorityContract(grants=("tool.result.transform",)),
        observability=EvidenceContract(descriptors=("guard.tool-result-spill.applied",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.body.guard.service import ToolGuardService

    service = ctx.require("tool_guards")
    if not isinstance(service, ToolGuardService):
        raise TypeError(f"tool_guards must be ToolGuardService, got {type(service).__name__}")
    service.add(
        ToolResultSpillGuard(max_inline_bytes=config.max_inline_bytes),
        id="tool-result-spill",
        order=20,
    )
