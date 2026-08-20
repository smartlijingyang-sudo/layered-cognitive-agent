"""SimpleBody plugin — registers into the BODIES registry seam."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import BODIES
from lca.contracts.protocols import Body
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="body.simple",
    requires=[BODIES.key],
    implements=[Body],
    layer="L1",
    effects="tools",
    description="Register SimpleBody as bodies['simple'].",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.layer1_cognitive.body.simple_body import SimpleBody

    ctx.register(BODIES.key, "simple", SimpleBody)
