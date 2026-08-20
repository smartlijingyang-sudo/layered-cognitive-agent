"""OtelTracer factory plugin (Tier-2).

创建 OTel TracerProvider + SpanProcessor 链，返回 ``OtelTracer`` adapter。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.ports import TracerBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-tracer-otel-factory",
    requires=["tracer_backends"],
    implements=[TracerBackend],
    layer="L0",
    effects="none",
    description="Register OtelTracer factory as tracer_backends['otel'].",
    test_suite="tests/test_tracer_plugin.py::test_provider_registers_otel_tracer",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

    from lca.layer0_infra.observability import (
        AttributePolicy,
        NamedRegistry,
        ObservabilitySettings,
    )
    from lca.layer0_infra.observability.tracer_backend import OtelTracer

    registry: NamedRegistry = ctx.require("tracer_backends")

    def _make_otel(settings: ObservabilitySettings | None = None, **_: Any) -> TracerBackend:
        cfg = settings or ObservabilitySettings()
        resource = Resource.create({"service.name": "lca"})
        provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
        # exporter 通过 ctx 注入（assemble 阶段完成）
        # 此处只构造 tracer；processor 由 assemble 阶段追加
        tracer = provider.get_tracer("lca")
        policy = AttributePolicy(verbosity=cfg.verbosity, redact=cfg.redact_enabled)
        return OtelTracer(tracer=tracer, policy=policy)

    registry.register("otel", _make_otel)
