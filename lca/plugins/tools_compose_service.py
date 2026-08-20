"""Tools Compose Service plugin — named factory ``tools.compose_service``.

Returns a fresh :class:`ToolsService` per composition. The Composer no
longer instantiates ``ToolsService()`` inline; it resolves a factory
through this plugin (``ctx.inject("tools.compose_service")()``).
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.infra import ToolRegistry
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_tools_service_compose() -> ToolRegistry:
    from lca.layer0_infra.capability.tools import ToolsService

    return ToolsService()


@plugin(
    name="tools.compose_service",
    provides=["tools.compose_service"],
    requires=[],
    implements=[ToolRegistry],
    layer="behavior",
    side_effects="tools",
    policy_class="observe",
    description="Compose-time ToolsService factory (one fresh instance per compose).",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named factory ``tools.compose_service``."""
    ctx.provide("tools.compose_service", build_tools_service_compose)
