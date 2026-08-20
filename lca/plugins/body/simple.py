"""SimpleBody plugin — named factory ``body.simple``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import Body
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="body.simple",
    provides=["body.simple"],
    implements=[Body],
    layer="L1",
    effects="tools",
    description="Provide the Body factory used by the Composer.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide the named Body factory ``body.simple``."""
    from lca.layer1_cognitive.body.simple_body import SimpleBody

    ctx.provide("body.simple", SimpleBody)
