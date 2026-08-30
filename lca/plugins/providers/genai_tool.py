"""ToolGenAIMapper provider plugin (Tier-2) —— ADR-0063 PR-10.

把 ``ToolGenAIMapper`` 注册到 ``genai_semantic_mapper`` seam。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.genai_semantic import GenAISemanticMapper
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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry, ToolGenAIMapper

    registry: NamedRegistry = ctx.require("genai_semantic_mapper")
    mapper = ToolGenAIMapper()
    registry.register(mapper.event_type, mapper)
    ctx.register("genai_semantic_mapper", mapper.event_type, mapper)
