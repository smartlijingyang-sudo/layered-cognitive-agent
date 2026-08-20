"""OtelProjector factory plugin (Tier-2).

把 ``OtelProjector`` 注册为 ``fact_readers`` 的 factory。
tracer 实例由 assemble 阶段按 kwarg 注入（典型来源：tracer_backend 工厂产物）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols import JournalProjector
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-reader-otel-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Register OtelProjector factory as fact_readers['otel'].",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_otel_reader",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry, ObservabilitySettings
    from lca.layer0_infra.observability.journal.otel_projector import OtelProjector

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_otel_reader(
        settings: ObservabilitySettings | None = None,
        *,
        tracer: Any = None,
        **_: Any,
    ) -> JournalProjector:
        # tracer 由 assemble 阶段按 kwarg 注入；此处不主动构造
        _ = settings
        return OtelProjector(tracer, genai_mapper_registry=None)

    registry.register("otel", _make_otel_reader)
