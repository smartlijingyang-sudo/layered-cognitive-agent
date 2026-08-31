"""LLM Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-llm-service",
    provides=["llm"],
    requires=[],
    implements=["LLMAdapter"],
    layer="L0",
    effects="none",
    description="Provide the LLM Definition service (ProviderDispatch + LLMAdapter).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-llm-service.checked', 'lca-llm-service.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.llm import LlmService

    ctx.provide("llm", LlmService())
