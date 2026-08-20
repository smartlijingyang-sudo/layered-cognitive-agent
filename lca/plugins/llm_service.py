"""LLM Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-llm-service",
    provides=["llm"],
    requires=[],
    implements=["LLMAdapter"],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Provide the LLM Definition service (ProviderDispatch + LLMAdapter).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.llm import LlmService

    ctx.provide("llm", LlmService())
