"""W3C trace context validator seam plugin (Tier-1) —— ADR-0065 PR-7。

声明 ``w3c_trace_context_validator`` capability;boot 后由 provider 注入
默认 ``DefaultW3CValidator``。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.w3c_trace_context import W3CTraceContextValidator
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-w3c-validator-seam",
    provides=["w3c_trace_context_validator"],
    implements=[W3CTraceContextValidator],
    layer="L0",
    effects="none",
    description="Provide W3C trace context validator (ADR-0065 §八 / PR-7).",
    test_suite="tests/test_seam_w3c_validator.py::test_seam_provides_default_validator",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability.w3c_validator import DefaultW3CValidator

    del config
    ctx.provide("w3c_trace_context_validator", DefaultW3CValidator())
