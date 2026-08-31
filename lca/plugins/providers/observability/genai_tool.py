"""ToolGenAIMapper provider plugin (Tier-2) —— ADR-0063 PR-10.

把 ``ToolGenAIMapper`` 注册到 ``genai_semantic_mapper`` seam。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.genai_semantic import GenAISemanticMapper
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-genai-tool-mapper",
    requires=["genai_semantic_mapper"],
    implements=[GenAISemanticMapper],
    layer="L0",
    effects="none",
    description="ToolInvoked → gen_ai.tool.* attribute mapper (PR-10).",
    test_suite="tests/test_genai_semantic.py::test_tool_mapper_registered",
    kind=PluginKind.PROVIDER,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-genai-tool-mapper.checked", "lca-genai-tool-mapper.served"),
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
    from lca.infrastructure.observability import NamedRegistry, ToolGenAIMapper

    registry: NamedRegistry = ctx.require("genai_semantic_mapper")
    mapper = ToolGenAIMapper()
    registry.register(mapper.event_type, mapper)
    ctx.register("genai_semantic_mapper", mapper.event_type, mapper)
