"""System Prompt Service Definition plugin — Tier-1.

The full SystemPromptService (with section assembler) is out of scope for
this minimal stub. Real implementation lives in lca/layer0_infra/system_prompt/service.py.
"""

from __future__ import annotations
from typing import Any
from lca.harness.plugin_api import plugin, PluginKind


class _MinimalSystemPromptService:
    """Minimal stub — replaced by full implementation in Chunk 2."""

    def assemble(self, role: str, **kwargs: object) -> str:
        return f"base_prompt_for({role})"


@plugin(
    id="lca-system-prompt-service",
    provides=["system_prompt"],
    layer="L0",
    effects="none",
    description="Minimal SystemPromptService stub — section assembler deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    ctx.provide("system_prompt", _MinimalSystemPromptService())
