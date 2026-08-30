"""SimpleBody plugin — registers into the BODIES registry seam."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import BODIES
from lca.contracts.protocols import Body
from lca.contracts.protocols.composition.logic_address import LogicAddress
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
    functional_group=FunctionalGroup.G7_EXECUTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.ACT_EXECUTE,
        scope=Scope.AGENT,
        authority=(BODIES.key,),
        evidence=("body.act.completed",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.cognition.body.simple_body import SimpleBody

    ctx.register(BODIES.key, "simple", SimpleBody)
