"""Tools Provider plugin — Tier-2 (tool factories)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.infra import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a"])


def _g2a_factory(run: object | None = None) -> list:
    from lca.layer0_infra.tools.default_set import build_default_tools

    bind = run if isinstance(run, dict) else {}
    return build_default_tools(
        store=bind.get("file_store"),
        bindings=bind.get("bindings"),
        sandbox=bind.get("sandbox"),
        search=bind.get("search"),
        skill_store=bind.get("skill_store"),
        fallback=False,
    )


@plugin(
    id="lca-tools-provider",
    requires=["tools"],
    implements=[Tool],
    layer="L0",
    effects="tools",
    description="Register Tool factories on the ToolsService Definition (forked per-run).",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if "g2a" in config.factories:
        ctx.inject("tools").register_factory("g2a", _g2a_factory)
