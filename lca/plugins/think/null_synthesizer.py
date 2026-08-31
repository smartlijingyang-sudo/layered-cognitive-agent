"""NullSynthesizer plugin — named factory ``synthesizer.null`` (ADR-0068 / 宪法 §3.4)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import Synthesizer
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-synthesizer-null",
    provides=["synthesizer.null"],
    implements=[Synthesizer],
    layer="L1",
    effects="none",
    description="Provide NullSynthesizer as ``synthesizer.null`` (ADR-0068 default).",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=("plugin.serve",),
        evidence=("lca-synthesizer-null.checked", "lca-synthesizer-null.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("synthesizer.null",),
        emits=("synthesizer.null.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullSynthesizer as ``synthesizer.null``."""
    from lca.cognition.brain.null_synthesizer import NullSynthesizer

    ctx.provide("synthesizer.null", NullSynthesizer)
