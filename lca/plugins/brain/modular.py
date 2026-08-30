"""ModularBrain strategy plugin — registers into BRAINS as 'modular'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import BRAINS
from lca.contracts.protocols import BrainFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.brain._standard_factory import (
    STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS,
    build_standard_cognitive_brain_factory,
)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-brain-modular",
    provides=[],
    requires=STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS,
    implements=[BrainFactory],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    functional_group=FunctionalGroup.G5_COGNITION,
    description="Register the standard cognitive Brain factory as brains['modular'].",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    factory = build_standard_cognitive_brain_factory(ctx)
    ctx.register(BRAINS.key, "modular", factory)
