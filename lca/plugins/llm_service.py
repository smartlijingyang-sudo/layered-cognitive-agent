"""LLM Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.harness.plugin_api import plugin, PluginKind


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
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.llm import LlmService

    ctx.provide("llm", LlmService())
