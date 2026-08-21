"""Tracer seam plugin (Tier-1).

声明 ``tracer_backends`` 注册中心；boot 后 ``providers/otel_tracer`` 把
``OtelTracer`` factory 注入。新增 tracer backend = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.ports import TracerBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("tracer_backends", NamedRegistry())
