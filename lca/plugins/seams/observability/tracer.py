"""Tracer seam plugin (Tier-1).

声明 ``tracer_backends`` 注册中心；boot 后 ``providers/otel_tracer`` 把
``OtelTracer`` factory 注入。新增 tracer backend = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.ports import TracerBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-tracer-seam",
    provides=["tracer_backends"],
    implements=[TracerBackend],
    layer="L0",
    effects="none",
    description="Provide the tracer_backends seam (facade plugin-ification).",
    test_suite="tests/test_tracer_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-tracer-seam.checked', 'lca-tracer-seam.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("tracer_backends", NamedRegistry())
